import base64


def is_image_file(filename):
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']


def is_pdf_file(filename):
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext == 'pdf'


def convert_image_to_base64(image_path):
    try:
        with open(image_path, 'rb') as image_file:
            image_data = image_file.read()
            base64_string = base64.b64encode(image_data).decode('utf-8')
            print(f"✓ Imagem convertida para base64: {len(base64_string)} caracteres")
            return base64_string
    except Exception as e:
        print(f"Erro ao converter imagem para base64: {e}")
        return None
