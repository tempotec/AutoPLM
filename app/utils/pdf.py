import os
import io
import base64
import re
import shutil
import PyPDF2
from PIL import Image


def _get_static_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'static'))


def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            print(f"\n{'='*80}")
            print(f"EXTRAÇÃO DE TEXTO DO PDF: {pdf_path}")
            print(f"Total de páginas: {len(pdf_reader.pages)}")
            print(f"{'='*80}")

            for page_num, page in enumerate(pdf_reader.pages, 1):
                page_text = page.extract_text()
                text += page_text
                print(f"\n--- Página {page_num} ---")
                print(f"Texto extraído ({len(page_text)} caracteres):")
                print(page_text[:500])
                if len(page_text) > 500:
                    print(f"... (mais {len(page_text) - 500} caracteres)")

            print(f"\n{'='*80}")
            print(f"TOTAL DE TEXTO EXTRAÍDO: {len(text)} caracteres")
            print(f"{'='*80}\n")
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        import traceback
        traceback.print_exc()
    if len(text.strip()) < 50:
        try:
            import pymupdf as fitz
            print(f"\n{'='*80}")
            print(f"PDF text fallback via PyMuPDF: {pdf_path}")
            print(f"{'='*80}")
            doc = fitz.open(pdf_path)
            fallback_text = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()
                fallback_text.append(page_text)
                print(f"\n--- Fallback page {page_num + 1} ---")
                print(f"Text length: {len(page_text)}")
            doc.close()
            fallback_text = "".join(fallback_text)
            if len(fallback_text.strip()) > len(text.strip()):
                text = fallback_text
            print(f"\n{'='*80}")
            print(f"TOTAL DE TEXTO FALLBACK: {len(fallback_text)} caracteres")
            print(f"{'='*80}\n")
        except Exception as e:
            print(f"Error extracting fallback text from PDF: {e}")
            import traceback
            traceback.print_exc()

    if len(text.strip()) < 50:
        try:
            import pymupdf as fitz
            import pytesseract
            tesseract_cmd = _configure_tesseract(pytesseract)
            if not tesseract_cmd:
                print("Tesseract binary not found. Install it or set TESSERACT_CMD.")
                return text
            print(f"\n{'='*80}")
            print(f"PDF OCR fallback via Tesseract: {pdf_path}")
            print(f"{'='*80}")
            doc = fitz.open(pdf_path)
            ocr_text_parts = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                try:
                    page_text = pytesseract.image_to_string(img, lang="por")
                except Exception:
                    page_text = pytesseract.image_to_string(img, lang="eng")
                ocr_text_parts.append(page_text)
                print(f"\n--- OCR page {page_num + 1} ---")
                print(f"Text length: {len(page_text)}")
            doc.close()
            ocr_text = "".join(ocr_text_parts)
            if len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text
            print(f"\n{'='*80}")
            print(f"TOTAL DE TEXTO OCR: {len(ocr_text)} caracteres")
            print(f"{'='*80}\n")
        except Exception as e:
            print(f"Error extracting OCR text from PDF: {e}")
            import traceback
            traceback.print_exc()

    return text


def normalize_ocr_text(text):
    if not text:
        return text
    text = text.replace("\x0c", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = text.replace("|", "I")
    return text.strip()


def _configure_tesseract(pytesseract):
    env_cmd = os.environ.get('TESSERACT_CMD')
    if env_cmd and os.path.exists(env_cmd):
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return env_cmd

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate

    cmd = shutil.which('tesseract')
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        return cmd

    return None


def extract_text_from_image(image_path):
    text = ""
    try:
        import pytesseract
        tesseract_cmd = _configure_tesseract(pytesseract)
        if not tesseract_cmd:
            print("Tesseract binary not found. Install it or set TESSERACT_CMD.")
            return text
        print(f"\n{'='*80}")
        print(f"OCR DE IMAGEM: {image_path}")
        print(f"{'='*80}")
        with Image.open(image_path) as img:
            def _preprocess(src):
                gray = src.convert("L")
                try:
                    from PIL import ImageOps, ImageFilter
                    gray = ImageOps.autocontrast(gray)
                    gray = gray.filter(ImageFilter.SHARPEN)
                except Exception:
                    pass
                bw = gray.point(lambda x: 0 if x < 160 else 255, "1")
                return bw.convert("L")

            def _ocr(src, label):
                try:
                    result = pytesseract.image_to_string(src, lang="por")
                except Exception:
                    result = pytesseract.image_to_string(src, lang="eng")
                print(f"OCR {label}: {len(result)} caracteres")
                return result

            variants = []
            variants.append(("original", img.copy()))
            variants.append(("preprocess", _preprocess(img)))

            upscale = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
            variants.append(("upscale2x_preprocess", _preprocess(upscale)))

            top_h = max(1, int(img.height * 0.35))
            top_crop = img.crop((0, 0, img.width, top_h))
            variants.append(("top35_preprocess", _preprocess(top_crop)))

            best_text = ""
            best_label = ""
            for label, variant in variants:
                result = _ocr(variant, label)
                if len(result) > len(best_text):
                    best_text = result
                    best_label = label

            text = normalize_ocr_text(best_text)
            if best_label:
                print(f"OCR selecionado: {best_label}")
        print(f"Texto OCR extraido: {len(text)} caracteres")
        print(f"{'='*80}\n")
    except Exception as e:
        print(f"Error extracting OCR text from image: {e}")
        import traceback
        traceback.print_exc()
    return text


def extract_images_from_pdf(pdf_path):
    images_data = []
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            print(f"\n{'='*80}")
            print(f"EXTRAÇÃO DE IMAGENS DO PDF")
            print(f"{'='*80}")

            for page_num, page in enumerate(pdf_reader.pages):
                if '/Resources' in page and '/XObject' in page['/Resources']:
                    xObject = page['/Resources']['/XObject'].get_object()
                    for obj_num, obj in enumerate(xObject):
                        if xObject[obj]['/Subtype'] == '/Image':
                            try:
                                width = xObject[obj]['/Width']
                                height = xObject[obj]['/Height']
                                size = (width, height)
                                data = xObject[obj].get_data()

                                colorspace_raw = xObject[obj].get('/ColorSpace', None)

                                if hasattr(colorspace_raw, 'get_object'):
                                    colorspace = colorspace_raw.get_object()
                                else:
                                    colorspace = colorspace_raw

                                try:
                                    if colorspace == '/DeviceRGB':
                                        img = Image.frombytes('RGB', size, data)
                                    elif colorspace == '/DeviceGray':
                                        img = Image.frombytes('L', size, data)
                                    elif colorspace == '/DeviceCMYK':
                                        img = Image.frombytes('CMYK', size, data)
                                        img = img.convert('RGB')
                                    elif isinstance(colorspace, list):
                                        colorspace_name = colorspace[0] if colorspace else None

                                        if colorspace_name == '/Indexed':
                                            try:
                                                base_colorspace = colorspace[1] if len(colorspace) > 1 else '/DeviceRGB'
                                                hival = int(colorspace[2]) if len(colorspace) > 2 else 255
                                                lookup_raw = colorspace[3] if len(colorspace) > 3 else None

                                                if lookup_raw and hasattr(lookup_raw, 'get_object'):
                                                    lookup = lookup_raw.get_object()
                                                else:
                                                    lookup = lookup_raw

                                                if hasattr(lookup, 'get_data'):
                                                    lookup_data = lookup.get_data()
                                                elif isinstance(lookup, bytes):
                                                    lookup_data = lookup
                                                elif hasattr(lookup, 'original_bytes'):
                                                    lookup_data = lookup.original_bytes
                                                elif isinstance(lookup, str):
                                                    lookup_data = lookup.encode('latin-1')
                                                else:
                                                    try:
                                                        lookup_data = bytes(lookup)
                                                    except:
                                                        print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: Lookup type desconhecido ({type(lookup)})")
                                                        img = Image.frombytes('P', size, data)
                                                        img = img.convert('RGB')

                                                img = Image.frombytes('P', size, data)

                                                if base_colorspace == '/DeviceRGB' or (isinstance(base_colorspace, str) and 'RGB' in base_colorspace):
                                                    palette = []
                                                    for i in range(min(256, hival + 1)):
                                                        idx = i * 3
                                                        if idx + 2 < len(lookup_data):
                                                            palette.extend([lookup_data[idx], lookup_data[idx + 1], lookup_data[idx + 2]])
                                                        else:
                                                            palette.extend([0, 0, 0])
                                                    while len(palette) < 768:
                                                        palette.extend([0, 0, 0])
                                                    img.putpalette(palette)
                                                    img = img.convert('RGB')
                                                else:
                                                    img = img.convert('RGB')

                                            except Exception as indexed_error:
                                                print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: Indexed ColorSpace - erro na paleta ({indexed_error})")
                                                continue

                                        elif colorspace_name == '/ICCBased':
                                            try:
                                                img = Image.frombytes('RGB', size, data)
                                            except:
                                                print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: ICCBased ColorSpace não suportado")
                                                continue
                                        else:
                                            try:
                                                img = Image.frombytes('RGB', size, data)
                                            except:
                                                print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: ColorSpace complexo ({colorspace_name})")
                                                continue
                                    else:
                                        try:
                                            img = Image.frombytes('RGB', size, data)
                                        except:
                                            print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: ColorSpace desconhecido ({colorspace})")
                                            continue

                                except Exception as color_error:
                                    print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: Erro ao processar ColorSpace - {color_error}")
                                    continue

                                buffered = io.BytesIO()
                                img.save(buffered, format="PNG")
                                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

                                area = width * height

                                images_data.append({
                                    'base64': img_base64,
                                    'page': page_num + 1,
                                    'width': width,
                                    'height': height,
                                    'area': area
                                })

                                print(f"  ✓ Página {page_num + 1}, Imagem {obj_num + 1}: {width}x{height}px (área: {area:,}px²)")

                            except Exception as e:
                                print(f"  ✗ Erro extraindo imagem da página {page_num + 1}: {e}")
                                continue

            images_data.sort(key=lambda x: x['area'], reverse=True)

            print(f"\n{'='*80}")
            print(f"TOTAL DE IMAGENS EXTRAÍDAS: {len(images_data)}")
            if images_data:
                print(f"Ordem de prioridade (por tamanho):")
                for i, img in enumerate(images_data[:5], 1):
                    print(f"  {i}. Página {img['page']}: {img['width']}x{img['height']}px (área: {img['area']:,}px²)")
            print(f"{'='*80}\n")

    except Exception as e:
        print(f"Error processing PDF for images: {e}")
        import traceback
        traceback.print_exc()

    return images_data


def generate_image_thumbnail(image_path, spec_id):
    try:
        import uuid

        print(f"\n{'='*80}")
        print(f"GERANDO THUMBNAIL DA IMAGEM: {image_path}")
        print(f"{'='*80}")

        img = Image.open(image_path)

        max_size = (800, 800)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        static_dir = _get_static_dir()
        thumbnails_dir = os.path.join(static_dir, 'thumbnails')
        os.makedirs(thumbnails_dir, exist_ok=True)

        thumbnail_filename = f"thumbnail_{spec_id}_{uuid.uuid4().hex[:8]}.png"
        thumbnail_path = os.path.join(thumbnails_dir, thumbnail_filename)

        img.save(thumbnail_path, 'PNG')

        thumbnail_url = f"/static/thumbnails/{thumbnail_filename}"
        print(f"✓ Thumbnail de imagem gerado com sucesso: {thumbnail_url}")
        print(f"{'='*80}\n")

        return thumbnail_url

    except Exception as e:
        print(f"Erro ao gerar thumbnail de imagem: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_pdf_thumbnail(pdf_path, spec_id):
    try:
        import pymupdf as fitz
        import uuid

        print(f"\n{'='*80}")
        print(f"GERANDO THUMBNAIL DO PDF: {pdf_path}")
        print(f"{'='*80}")

        doc = fitz.open(pdf_path)

        if len(doc) == 0:
            print("PDF não tem páginas")
            return None

        page = doc[0]

        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)

        static_dir = _get_static_dir()
        thumbnails_dir = os.path.join(static_dir, 'thumbnails')
        os.makedirs(thumbnails_dir, exist_ok=True)

        thumbnail_filename = f"thumbnail_{spec_id}_{uuid.uuid4().hex[:8]}.png"
        thumbnail_path = os.path.join(thumbnails_dir, thumbnail_filename)

        pix.save(thumbnail_path)
        doc.close()

        thumbnail_url = f"/static/thumbnails/{thumbnail_filename}"
        print(f"✓ Thumbnail gerado com sucesso: {thumbnail_url}")
        print(f"{'='*80}\n")

        return thumbnail_url

    except Exception as e:
        print(f"Erro ao gerar thumbnail: {e}")
        import traceback
        traceback.print_exc()
        return None
