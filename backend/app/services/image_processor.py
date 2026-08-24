from __future__ import annotations

import io
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError


BASE_DIR = Path(__file__).resolve().parents[2]
JOBS_DIR = BASE_DIR / "storage" / "image_jobs"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OUTPUT_FORMATS = {"webp": ("WEBP", ".webp"), "jpeg": ("JPEG", ".jpg"), "png": ("PNG", ".png")}
MAX_FILE_SIZE = 30 * 1024 * 1024
MAX_FILES = 60


def _safe_stem(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("ё", "е")
    translit = str.maketrans({
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l",
        "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
        "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch",
        "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
        "ю": "yu", "я": "ya",
    })
    value = value.translate(translit)
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"[-_]{2,}", "-", value).strip("-_")
    return value or "image"


def _build_name(template: str, index: int, source_name: str) -> str:
    source_stem = _safe_stem(Path(source_name).stem)
    template = (template or "image-{n}").strip()
    prepared = template.replace("{n}", f"{index:02d}").replace("{name}", source_stem)
    prepared = _safe_stem(prepared)
    if "{n}" not in template and index > 1:
        prepared = f"{prepared}-{index:02d}"
    return prepared


def _save_image(image: Image.Image, target: Path, output_format: str, quality: int) -> None:
    pil_format, _ = OUTPUT_FORMATS[output_format]
    save_kwargs: dict[str, Any] = {}

    if output_format in {"webp", "jpeg"}:
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    if output_format == "webp":
        save_kwargs["method"] = 6
    if output_format == "png":
        save_kwargs["optimize"] = True

    if output_format == "jpeg" and image.mode not in {"RGB", "L"}:
        background = Image.new("RGB", image.size, "white")
        if "A" in image.getbands():
            background.paste(image, mask=image.getchannel("A"))
        else:
            background.paste(image)
        image = background

    image.save(target, pil_format, **save_kwargs)


async def process_images(
    files: list[UploadFile],
    *,
    max_width: int,
    output_format: str,
    quality: int,
    name_template: str,
) -> dict[str, Any]:
    if not files:
        raise ValueError("Добавьте хотя бы одно изображение")
    if len(files) > MAX_FILES:
        raise ValueError(f"За один раз можно обработать не более {MAX_FILES} изображений")
    if output_format not in OUTPUT_FORMATS:
        raise ValueError("Неподдерживаемый формат")
    if not 320 <= max_width <= 6000:
        raise ValueError("Максимальная ширина должна быть от 320 до 6000 px")
    if not 30 <= quality <= 100:
        raise ValueError("Качество должно быть от 30 до 100")

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    output_dir = job_dir / "files"
    output_dir.mkdir(parents=True, exist_ok=False)

    results: list[dict[str, Any]] = []
    total_before = 0
    total_after = 0
    used_names: set[str] = set()

    try:
        for index, upload in enumerate(files, start=1):
            source_name = upload.filename or f"image-{index}"
            extension = Path(source_name).suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                raise ValueError(f"{source_name}: поддерживаются JPG, PNG и WebP")

            raw = await upload.read()
            if len(raw) > MAX_FILE_SIZE:
                raise ValueError(f"{source_name}: файл больше 30 МБ")
            total_before += len(raw)

            try:
                image = Image.open(io.BytesIO(raw))
                image.load()
            except (UnidentifiedImageError, OSError) as exc:
                raise ValueError(f"{source_name}: не удалось прочитать изображение") from exc

            image = ImageOps.exif_transpose(image)
            original_width, original_height = image.size
            if original_width > max_width:
                ratio = max_width / original_width
                new_size = (max_width, max(1, round(original_height * ratio)))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            output_width, output_height = image.size

            stem = _build_name(name_template, index, source_name)
            candidate = stem
            duplicate_index = 2
            while candidate in used_names:
                candidate = f"{stem}-{duplicate_index:02d}"
                duplicate_index += 1
            used_names.add(candidate)

            _, output_extension = OUTPUT_FORMATS[output_format]
            output_name = f"{candidate}{output_extension}"
            output_path = output_dir / output_name
            _save_image(image, output_path, output_format, quality)
            after_size = output_path.stat().st_size
            total_after += after_size

            results.append(
                {
                    "source_name": source_name,
                    "output_name": output_name,
                    "before_bytes": len(raw),
                    "after_bytes": after_size,
                    "saved_percent": round((1 - after_size / len(raw)) * 100, 1) if raw else 0,
                    "original_width": original_width,
                    "original_height": original_height,
                    "output_width": output_width,
                    "output_height": output_height,
                }
            )

        if len(results) > 1:
            zip_path = job_dir / "contentdesk-images.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for item in output_dir.iterdir():
                    archive.write(item, arcname=item.name)

        return {
            "job_id": job_id,
            "count": len(results),
            "total_before_bytes": total_before,
            "total_after_bytes": total_after,
            "saved_percent": round((1 - total_after / total_before) * 100, 1) if total_before else 0,
            "files": results,
        }
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


def get_job_zip(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise ValueError("Некорректный идентификатор")
    path = JOBS_DIR / job_id / "contentdesk-images.zip"
    if not path.exists():
        raise FileNotFoundError
    return path


def get_job_file(job_id: str, filename: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise ValueError("Некорректный идентификатор")
    safe_name = Path(filename).name
    if safe_name != filename:
        raise ValueError("Некорректное имя файла")
    path = JOBS_DIR / job_id / "files" / safe_name
    if not path.exists() or not path.is_file():
        raise FileNotFoundError
    return path
