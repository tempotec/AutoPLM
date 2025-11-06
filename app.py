import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, TextAreaField, PasswordField, SelectField, SubmitField, DateField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import PyPDF2
from functools import wraps
import base64
from PIL import Image
import io

# Import OpenAI functionality
from openai import OpenAI

# Import Replit Object Storage
from replit.object_storage import Client

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET')
if not app.config['SECRET_KEY']:
    raise RuntimeError("SESSION_SECRET environment variable is required")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Verifica conexões antes de usar
    'pool_recycle': 3600,  # Reconecta a cada hora
    'pool_timeout': 30,  # Timeout de 30 segundos para conexões
}
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize extensions
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# Make CSRF token available in templates
from flask_wtf.csrf import generate_csrf


@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)


@app.template_filter('from_json')
def from_json_filter(value):
    import json
    try:
        return json.loads(value) if value else []
    except:
        return []


# Initialize OpenAI client
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), default='stylist')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship with specifications
    specifications = db.relationship('Specification',
                                     backref='user',
                                     lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200))
    contact_name = db.Column(db.String(200))
    contact_email = db.Column(db.String(200))
    contact_phone = db.Column(db.String(50))
    materials_json = db.Column(db.Text)  # JSON string of materials with colors
    avatar_color = db.Column(db.String(20), default='#667eea')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with user
    user = db.relationship('User', backref=db.backref('suppliers', lazy=True))


class Collection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default='em_desenvolvimento')  # em_desenvolvimento, finalizada
    cover_image = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with user
    user = db.relationship('User', backref=db.backref('collections', lazy=True))


class Specification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    collection_id = db.Column(db.Integer, db.ForeignKey('collection.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)
    pdf_filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 1. Identificação da Peça
    ref_souq = db.Column(db.String(100))
    description = db.Column(db.Text)
    collection = db.Column(db.String(100))
    supplier = db.Column(db.String(100))
    corner = db.Column(db.String(100))

    # 2. Informações Comerciais
    target_price = db.Column(db.String(100))
    store_month = db.Column(db.String(200))
    delivery_cd_month = db.Column(db.String(200))

    # 3. Prazos e Entregas
    tech_sheet_delivery_date = db.Column(db.Date)
    pilot_delivery_date = db.Column(db.Date)
    showcase_for = db.Column(db.String(200))

    # 4. Equipe Envolvida
    stylists = db.Column(db.String(200))

    # 5. Matéria-Prima e Aviamentos
    composition = db.Column(db.Text)
    colors = db.Column(db.Text)
    tags_kit = db.Column(db.Text)

    # 6. Especificações Técnicas da Modelagem
    pilot_size = db.Column(db.String(50))
    body_length = db.Column(db.String(100))
    sleeve_length = db.Column(db.String(100))
    hem_width = db.Column(db.String(100))
    shoulder_to_shoulder = db.Column(db.String(100))
    bust = db.Column(db.String(100))
    waist = db.Column(db.String(100))
    straight_armhole = db.Column(db.String(100))
    neckline_depth = db.Column(db.String(100))
    openings_details = db.Column(db.Text)
    finishes = db.Column(db.Text)

    # 7. Design e Estilo
    technical_drawing = db.Column(db.Text)
    reference_photos = db.Column(db.Text)
    specific_details = db.Column(db.Text)

    # Generated technical drawing
    technical_drawing_url = db.Column(db.String(500))
    
    # PDF thumbnail for preview
    pdf_thumbnail = db.Column(db.String(500))

    # Raw extracted text and status
    raw_extracted_text = db.Column(db.Text)
    processing_status = db.Column(
        db.String(50),
        default='pending')  # pending, processing, completed, error
    
    # Product status workflow
    status = db.Column(
        db.String(50),
        default='draft')  # draft, in_development, approved, in_production
    
    # Relationship to collection and supplier
    collection_obj = db.relationship('Collection', backref='specifications', lazy=True)
    supplier_obj = db.relationship('Supplier', backref='specifications', lazy=True)


# Forms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class CreateUserForm(FlaskForm):
    username = StringField('Username',
                           validators=[DataRequired(),
                                       Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password',
                             validators=[DataRequired(),
                                         Length(min=6)])
    role = SelectField('Perfil',
                       choices=[('stylist', 'Estilista'), ('admin', 'Administrador')],
                       default='stylist')
    submit = SubmitField('Create User')


class SettingsForm(FlaskForm):
    username = StringField('Nome Completo', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Salvar Alterações')


class UploadPDFForm(FlaskForm):
    collection = StringField('Coleção', validators=[DataRequired()])
    collection_id = SelectField('Vincular à Coleção', coerce=int, validators=[])
    supplier_id = SelectField('Fornecedor', coerce=int, validators=[])
    stylist = StringField('Estilista')
    pdf_file = FileField(
        'File',
        validators=[FileRequired(),
                    FileAllowed(['pdf', 'jpg', 'jpeg', 'png'], 'Apenas PDF ou imagens (JPG, PNG)!')])
    submit = SubmitField('Upload and Process')


class SpecificationForm(FlaskForm):
    # 1. Identificação da Peça
    ref_souq = StringField('Referência (REF SOUQ)')
    description = TextAreaField('Descrição')
    collection = StringField('Coleção')
    collection_id = SelectField('Vincular à Coleção', coerce=int, validators=[])
    supplier = StringField('Fornecedor')
    corner = StringField('Corner')

    # 2. Informações Comerciais
    target_price = StringField('Target Price')
    store_month = StringField('Mês Loja')
    delivery_cd_month = StringField('Mês Entrega CD')

    # 3. Prazos e Entregas
    tech_sheet_delivery_date = DateField('Data de Entrega Ficha Técnica')
    pilot_delivery_date = DateField('Data de Entrega Piloto')
    showcase_for = StringField('Mostruário Para')

    # 4. Equipe Envolvida
    stylists = StringField('Estilista(s)')

    # 5. Matéria-Prima e Aviamentos
    composition = TextAreaField('Composição')
    colors = TextAreaField('Cores')
    tags_kit = TextAreaField('Kit Etiquetas + Tag + Pendurador Cabide')

    # 6. Especificações Técnicas da Modelagem
    pilot_size = StringField('Tamanho da Piloto')
    body_length = StringField('Comprimento corpo')
    sleeve_length = StringField('Comprimento da manga')
    hem_width = StringField('Largura da barra')
    shoulder_to_shoulder = StringField('Ombro a ombro')
    bust = StringField('Busto')
    waist = StringField('Cintura')
    straight_armhole = StringField('Cava reta')
    neckline_depth = StringField('Profundidade do decote')
    openings_details = TextAreaField('Aberturas ou detalhes')
    finishes = TextAreaField('Acabamentos')

    # 7. Design e Estilo
    technical_drawing = TextAreaField('Desenho técnico')
    reference_photos = TextAreaField('Fotos de referência / protótipo')
    specific_details = TextAreaField('Detalhes específicos')

    submit = SubmitField('Save Specification')


# Helper functions
def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Admin access required.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)

    return decorated_function


def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def is_image_file(filename):
    """Check if file is an image based on extension"""
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']


def is_pdf_file(filename):
    """Check if file is a PDF based on extension"""
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext == 'pdf'


def convert_image_to_base64(image_path):
    """Convert image file to base64 string"""
    import base64
    try:
        with open(image_path, 'rb') as image_file:
            image_data = image_file.read()
            base64_string = base64.b64encode(image_data).decode('utf-8')
            print(f"✓ Imagem convertida para base64: {len(base64_string)} caracteres")
            return base64_string
    except Exception as e:
        print(f"Erro ao converter imagem para base64: {e}")
        return None


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
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
                print(page_text[:500])  # Primeiros 500 caracteres
                if len(page_text) > 500:
                    print(f"... (mais {len(page_text) - 500} caracteres)")

            print(f"\n{'='*80}")
            print(f"TOTAL DE TEXTO EXTRAÍDO: {len(text)} caracteres")
            print(f"{'='*80}\n")
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        import traceback
        traceback.print_exc()
    return text


def extract_images_from_pdf(pdf_path):
    """Extract images from PDF and return as base64 encoded strings with metadata"""
    images_data = []
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            print(f"\n{'='*80}")
            print(f"EXTRAÇÃO DE IMAGENS DO PDF")
            print(f"{'='*80}")

            for page_num, page in enumerate(pdf_reader.pages):
                # Try to extract images from page
                if '/Resources' in page and '/XObject' in page['/Resources']:
                    xObject = page['/Resources']['/XObject'].get_object()
                    for obj_num, obj in enumerate(xObject):
                        if xObject[obj]['/Subtype'] == '/Image':
                            try:
                                # Get image data
                                width = xObject[obj]['/Width']
                                height = xObject[obj]['/Height']
                                size = (width, height)
                                data = xObject[obj].get_data()

                                # Convert to PIL Image - Support multiple ColorSpace formats
                                colorspace_raw = xObject[obj].get('/ColorSpace', None)
                                
                                # Dereference indirect objects (critical for Indexed color spaces)
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
                                        # Convert CMYK to RGB
                                        img = Image.frombytes('CMYK', size, data)
                                        img = img.convert('RGB')
                                    elif isinstance(colorspace, list):
                                        # Handle Indexed or ICCBased color spaces
                                        colorspace_name = colorspace[0] if colorspace else None
                                        
                                        if colorspace_name == '/Indexed':
                                            # Indexed color space: [/Indexed base_colorspace hival lookup]
                                            try:
                                                base_colorspace = colorspace[1] if len(colorspace) > 1 else '/DeviceRGB'
                                                hival = int(colorspace[2]) if len(colorspace) > 2 else 255
                                                lookup_raw = colorspace[3] if len(colorspace) > 3 else None
                                                
                                                # Dereference lookup if it's an indirect object
                                                if lookup_raw and hasattr(lookup_raw, 'get_object'):
                                                    lookup = lookup_raw.get_object()
                                                else:
                                                    lookup = lookup_raw
                                                
                                                # Get lookup data - handle PyPDF2 ByteStringObject
                                                if hasattr(lookup, 'get_data'):
                                                    # Stream object
                                                    lookup_data = lookup.get_data()
                                                elif isinstance(lookup, bytes):
                                                    # Direct bytes
                                                    lookup_data = lookup
                                                elif hasattr(lookup, 'original_bytes'):
                                                    # PyPDF2 ByteStringObject
                                                    lookup_data = lookup.original_bytes
                                                elif isinstance(lookup, str):
                                                    # String - encode as latin-1 (PDF standard encoding)
                                                    lookup_data = lookup.encode('latin-1')
                                                else:
                                                    # Unknown type - try to convert
                                                    try:
                                                        lookup_data = bytes(lookup)
                                                    except:
                                                        print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: Lookup type desconhecido ({type(lookup)})")
                                                        # Try without palette
                                                        img = Image.frombytes('P', size, data)
                                                        img = img.convert('RGB')
                                                
                                                # Create palette image
                                                img = Image.frombytes('P', size, data)
                                                
                                                # Build PIL palette from lookup data
                                                # Palette format depends on base colorspace
                                                if base_colorspace == '/DeviceRGB' or (isinstance(base_colorspace, str) and 'RGB' in base_colorspace):
                                                    # RGB palette: 3 bytes per color (R,G,B)
                                                    palette = []
                                                    for i in range(min(256, hival + 1)):
                                                        idx = i * 3
                                                        if idx + 2 < len(lookup_data):
                                                            palette.extend([lookup_data[idx], lookup_data[idx+1], lookup_data[idx+2]])
                                                        else:
                                                            palette.extend([0, 0, 0])
                                                    # Pad to 256 colors
                                                    while len(palette) < 768:
                                                        palette.extend([0, 0, 0])
                                                    img.putpalette(palette)
                                                    img = img.convert('RGB')
                                                else:
                                                    # For other base colorspaces, try direct conversion
                                                    img = img.convert('RGB')
                                                    
                                            except Exception as indexed_error:
                                                print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: Indexed ColorSpace - erro na paleta ({indexed_error})")
                                                continue
                                        
                                        elif colorspace_name == '/ICCBased':
                                            # ICC-based color space - try RGB as fallback
                                            try:
                                                img = Image.frombytes('RGB', size, data)
                                            except:
                                                print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: ICCBased ColorSpace não suportado")
                                                continue
                                        else:
                                            # Other complex color spaces - try RGB fallback
                                            try:
                                                img = Image.frombytes('RGB', size, data)
                                            except:
                                                print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: ColorSpace complexo ({colorspace_name})")
                                                continue
                                    else:
                                        # Unknown color space - try RGB as last resort
                                        try:
                                            img = Image.frombytes('RGB', size, data)
                                        except:
                                            print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: ColorSpace desconhecido ({colorspace})")
                                            continue
                                
                                except Exception as color_error:
                                    print(f"  ⚠️ Página {page_num + 1}, Imagem {obj_num + 1}: Erro ao processar ColorSpace - {color_error}")
                                    continue

                                # Convert to base64
                                buffered = io.BytesIO()
                                img.save(buffered, format="PNG")
                                img_base64 = base64.b64encode(
                                    buffered.getvalue()).decode('utf-8')

                                # Calculate image size to prioritize larger images (photos vs small icons)
                                area = width * height

                                images_data.append({
                                    'base64': img_base64,
                                    'page': page_num + 1,
                                    'width': width,
                                    'height': height,
                                    'area': area
                                })

                                print(
                                    f"  ✓ Página {page_num + 1}, Imagem {obj_num + 1}: {width}x{height}px (área: {area:,}px²)"
                                )

                            except Exception as e:
                                print(
                                    f"  ✗ Erro extraindo imagem da página {page_num + 1}: {e}"
                                )
                                continue

            # Sort images by area (larger images first - likely to be the main garment photos)
            images_data.sort(key=lambda x: x['area'], reverse=True)

            print(f"\n{'='*80}")
            print(f"TOTAL DE IMAGENS EXTRAÍDAS: {len(images_data)}")
            if images_data:
                print(f"Ordem de prioridade (por tamanho):")
                for i, img in enumerate(images_data[:5], 1):
                    print(
                        f"  {i}. Página {img['page']}: {img['width']}x{img['height']}px (área: {img['area']:,}px²)"
                    )
            print(f"{'='*80}\n")

    except Exception as e:
        print(f"Error processing PDF for images: {e}")
        import traceback
        traceback.print_exc()

    # Return complete image data (not just base64)
    return images_data


def generate_pdf_thumbnail(pdf_path, spec_id):
    """Generate a thumbnail from the first page of a PDF"""
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
        
        thumbnail_filename = f"thumbnail_{spec_id}_{uuid.uuid4().hex[:8]}.png"
        thumbnail_path = os.path.join('static', 'thumbnails', thumbnail_filename)
        
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


def analyze_images_with_gpt4_vision(images_base64):
    """Use GPT-4 Vision to analyze garment images with structured JSON output"""
    if not images_base64:
        print("No images provided for GPT-4 Vision analysis")
        return None

    if not openai_client:
        print("OpenAI client not initialized")
        return None

    try:
        print(f"Analyzing {len(images_base64)} images with GPT-4 Vision (structured JSON output)...")

        # Build messages with images - Professional structured prompt
        content = [{
            "type": "text",
            "text": """Você é um especialista técnico de vestuário. Analise ATÉ 3 imagens e descreva APENAS UMA peça: a mais PROEMINENTE da primeira imagem (maior área de pixels do corpo da peça). Ignore outras peças, pessoas, rostos e o fundo. Não descreva características pessoais.

⚠️ Precisão:
- Quando algo não pode ser visto com clareza, escreva exatamente "nao_visivel".
- Nunca invente medidas reais em cm sem referência explícita. Prefira relações visuais (ex.: "punho parece 2–3x a largura do pesponto").
- Use termos técnicos (PT-BR) e normalize enums (ex.: gola={careca,V,role,redonda,colarinho,polo,quadrada,canoa,ombro_a_ombro}).

Procedimento em 3 PASSOS (obrigatório):
1) MACRO: identifique tipo de peça e categoria (malha/tricô, tecido plano, jeans).
2) VARREDURA POR REGIÕES (ordem e "lupa"):
   - Decote/gola → placket/vistas → ombro/ombreira → cava → mangas → punhos → corpo/frente → bolsos frente → recortes/penses → barra → costas completas → gola/capuz costas → centro costas → recortes/penses costas → bolsos costas → barra costas → interior visível (forro/entretela/vivos).
   Para cada região, examine bordas, quinas, encontros, rebatidos, pespontos, travetes/bartacks, folgas e simetria E/D.
3) VARREDURA TRANSVERSAL (categorias de detalhe):
   - Fechamentos (tipo, posição exata, quantidade, direção de abotoamento).
   - Componentes pequenos: casas (forma, posição e distância da borda), botões (diâmetro relativo), ilhoses, rebites, colchetes, zíper (invisível/aparente, espiral/dente, cursor, puxador).
   - Costuras/acabamentos: tipo de ponto (reta, overlock 3/4 fios, cobertura), número de passadas (simples/duplo/tríplice), distância de rebatido da borda, largura de viés/debrum, largura de ribana/bainha, limpeza interna visível.
   - Modelagem/volume: franzidos, pregas, nervuras/canelados, godê, evasê, ombro caído, raglan.
   - Padronagens/texturas: direção do fio/canelado, disposição de tranças, rapport aparente.
   - Etiquetas/elementos externos: etiqueta de marca aparente, patches, bordados, termocolantes.
   - Assimetria e diferenças Frente vs Costas; Esquerda vs Direita (se houver).

SAÍDA: responda SOMENTE um JSON válido com este esquema (preencha tudo que conseguir; use "nao_visivel" quando não der):

{
  "identificacao": {
    "tipo_peca": "",
    "categoria": "",
    "confianca": 0.0
  },
  "visoes": {
    "frente": "...",
    "costas": "...",
    "mangas": "..."
  },
  "gola_decote": {
    "tipo": "",
    "altura_visual": "",
    "abertura_largura_visual": "",
    "acabamento": "",
    "detalhes": "",
    "confianca": 0.0
  },
  "mangas": {
    "comprimento": "",
    "modelo": "",
    "cava": "",
    "copa_modelagem": "",
    "punho": {
      "existe": true,
      "tipo": "",
      "largura_visual": "",
      "fechamento": ""
    },
    "pala_ou_recorte": "",
    "confianca": 0.0
  },
  "corpo": {
    "comprimento_visual": "",
    "caimento": "",
    "recortes": "...",
    "pences_pregas_franzidos": "...",
    "simetria_ED": "",
    "observacoes": ""
  },
  "fechamentos": {
    "tipo": "",
    "posicao": "",
    "quantidade_botoes": "nao_visivel",
    "botoes_espacamento_relativo": "",
    "direcao_abotoamento": "nao_visivel",
    "ziper": {
      "visibilidade": "nao_visivel",
      "tipo_dente": "nao_visivel",
      "comprimento_visual": ""
    }
  },
  "bolsos": {
    "existe": false,
    "lista": []
  },
  "barra_hem": {
    "formato": "",
    "acabamento": "",
    "largura_visual": "",
    "aberturas_fendas": ""
  },
  "textura_padronagem": {
    "tipo_trico_malha": "nao_visivel",
    "direcao": "nao_visivel",
    "rapport_ou_repeticao": "",
    "contraste_linha_pesponto": ""
  },
  "acabamentos_especiais": [],
  "diferencas_frente_costas": "...",
  "itens_nao_visiveis_ou_ambigos": [],
  "conclusao_checklist": {
    "varredura_regioes_ok": true,
    "varredura_transversal_ok": true,
    "campos_pendentes": []
  }
}

Retorne SOMENTE o JSON, sem texto adicional."""
        }]

        # Add all images
        for img_b64 in images_base64[:3]:  # Limit to first 3 images
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                    "detail": "high"
                }
            })

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": content
            }],
            response_format={"type": "json_object"},  # Force JSON output
            max_tokens=3000  # Increased for comprehensive structured analysis
        )

        json_response = response.choices[0].message.content
        
        # Parse and validate JSON
        try:
            analysis_data = json.loads(json_response)
            print(f"\n{'='*80}")
            print(f"ANÁLISE VISUAL GPT-4o (JSON ESTRUTURADO)")
            print(f"{'='*80}")
            print(f"Tipo de peça: {analysis_data.get('identificacao', {}).get('tipo_peca', 'N/A')}")
            print(f"Categoria: {analysis_data.get('identificacao', {}).get('categoria', 'N/A')}")
            print(f"Confiança: {analysis_data.get('identificacao', {}).get('confianca', 0.0)}")
            print(f"Gola/Decote: {analysis_data.get('gola_decote', {}).get('tipo', 'N/A')}")
            print(f"Mangas: {analysis_data.get('mangas', {}).get('comprimento', 'N/A')} - {analysis_data.get('mangas', {}).get('modelo', 'N/A')}")
            print(f"Fechamentos: {analysis_data.get('fechamentos', {}).get('tipo', 'N/A')}")
            print(f"{'='*80}\n")
            return analysis_data
        except json.JSONDecodeError as e:
            # FALLBACK: If JSON parsing fails, return raw text (legacy format)
            print(f"⚠️ Erro ao parsear JSON - usando fallback para texto bruto")
            print(f"Erro JSON: {e}")
            print(f"Retornando texto livre para compatibilidade...")
            # Return as plain string - build_technical_drawing_prompt() handles both formats
            return json_response

    except Exception as e:
        print(f"Error analyzing images with GPT-4 Vision: {e}")
        import traceback
        traceback.print_exc()
        return None


def has_technical_measurements(spec):
    """
    Check if specification has technical measurements for dimensioned drawing.
    Returns True if at least one measurement field is populated.
    """
    measurement_fields = [
        'body_length', 'bust', 'hem_width', 'shoulder_to_shoulder',
        'neckline_depth', 'sleeve_length', 'waist', 'straight_armhole'
    ]
    
    for field in measurement_fields:
        value = getattr(spec, field, None)
        if value and str(value).strip():
            return True
    
    return False


def build_technical_drawing_prompt(spec, visual_analysis=None):
    """Build professional technical flat sketch prompt for GPT-Image-1
    Generates clean flat sketch WITHOUT dimensions, POMs, or cotas.
    
    Args:
        spec: Specification database object
        visual_analysis: Structured JSON dict from GPT-4o Vision analysis (or legacy text string)
    """

    # Determine garment type from description
    garment_type = spec.description or "peça de vestuário"

    # Build material and composition info
    material_info = spec.composition or "malha/tecido padrão"

    # Extract additional material details if available
    material_details = ""
    if "tricô" in material_info.lower() or "malha" in material_info.lower():
        material_details = "Malha/tricô - representar textura com traço técnico"
    
    print(f"\n{'='*80}")
    print(f"GERANDO DESENHO TÉCNICO: Flat sketch limpo SEM COTAGEM")
    print(f"{'='*80}\n")

    # Build constructive details
    constructive_details = []
    if spec.finishes:
        constructive_details.append(f"Acabamentos: {spec.finishes}")
    if spec.openings_details:
        constructive_details.append(f"Fechamentos: {spec.openings_details}")

    details_text = " | ".join(
        constructive_details
    ) if constructive_details else "detalhes conforme análise visual"

    # Build visual reference section - ENHANCED for structured JSON
    visual_section = ""
    if visual_analysis:
        # Check if it's structured JSON or legacy text
        if isinstance(visual_analysis, dict):
            # STRUCTURED JSON - Build detailed description from fields
            ident = visual_analysis.get('identificacao', {})
            gola = visual_analysis.get('gola_decote', {})
            mangas = visual_analysis.get('mangas', {})
            corpo = visual_analysis.get('corpo', {})
            fechamentos = visual_analysis.get('fechamentos', {})
            bolsos = visual_analysis.get('bolsos', {})
            barra = visual_analysis.get('barra_hem', {})
            textura = visual_analysis.get('textura_padronagem', {})
            
            visual_parts = []
            
            # Identificação
            if ident.get('tipo_peca'):
                visual_parts.append(f"TIPO: {ident['tipo_peca']} ({ident.get('categoria', 'N/A')})")
            
            # Gola/Decote - CRÍTICO
            if gola.get('tipo') and gola['tipo'] != 'nao_visivel':
                gola_desc = f"GOLA/DECOTE: {gola['tipo']}"
                if gola.get('altura_visual') and gola['altura_visual'] != 'nao_visivel':
                    gola_desc += f" - altura {gola['altura_visual']}"
                if gola.get('acabamento'):
                    gola_desc += f" - acabamento: {gola['acabamento']}"
                if gola.get('detalhes'):
                    gola_desc += f" - {gola['detalhes']}"
                visual_parts.append(gola_desc)
            
            # Mangas - CRÍTICO
            if mangas.get('comprimento') and mangas['comprimento'] != 'nao_visivel':
                manga_desc = f"MANGAS: {mangas['comprimento']}"
                if mangas.get('modelo') and mangas['modelo'] != 'nao_visivel':
                    manga_desc += f" - modelo {mangas['modelo']}"
                if mangas.get('cava'):
                    manga_desc += f" - cava {mangas['cava']}"
                
                punho = mangas.get('punho', {})
                if punho.get('existe') and punho.get('tipo'):
                    manga_desc += f" - punho {punho['tipo']}"
                    if punho.get('largura_visual'):
                        manga_desc += f" ({punho['largura_visual']})"
                
                visual_parts.append(manga_desc)
            
            # Corpo
            if corpo.get('comprimento_visual'):
                corpo_desc = f"CORPO: comprimento {corpo['comprimento_visual']}"
                if corpo.get('caimento'):
                    corpo_desc += f" - caimento {corpo['caimento']}"
                if corpo.get('recortes'):
                    corpo_desc += f" - recortes: {corpo['recortes']}"
                visual_parts.append(corpo_desc)
            
            # Fechamentos - MUITO IMPORTANTE
            if fechamentos.get('tipo') and fechamentos['tipo'] != 'nao_visivel':
                fech_desc = f"FECHAMENTOS: {fechamentos['tipo']}"
                if fechamentos.get('posicao'):
                    fech_desc += f" na {fechamentos['posicao']}"
                if fechamentos.get('quantidade_botoes') and fechamentos['quantidade_botoes'] != 'nao_visivel':
                    fech_desc += f" - {fechamentos['quantidade_botoes']} botões"
                if fechamentos.get('botoes_espacamento_relativo'):
                    fech_desc += f" ({fechamentos['botoes_espacamento_relativo']})"
                
                ziper = fechamentos.get('ziper', {})
                if ziper.get('visibilidade') and ziper['visibilidade'] != 'nao_visivel':
                    fech_desc += f" - zíper {ziper['visibilidade']}"
                
                visual_parts.append(fech_desc)
            
            # Bolsos
            if bolsos.get('existe') and bolsos.get('lista'):
                for bolso in bolsos['lista']:
                    # Handle both dict and string formats
                    if isinstance(bolso, dict):
                        bolso_desc = f"BOLSO: {bolso.get('tipo', 'N/A')}"
                        if bolso.get('posicao'):
                            bolso_desc += f" - {bolso['posicao']}"
                        if bolso.get('dimensao_visual'):
                            bolso_desc += f" ({bolso['dimensao_visual']})"
                        visual_parts.append(bolso_desc)
                    elif isinstance(bolso, str):
                        visual_parts.append(f"BOLSO: {bolso}")
            
            # Barra
            if barra.get('formato'):
                barra_desc = f"BARRA: {barra['formato']}"
                if barra.get('acabamento'):
                    barra_desc += f" - acabamento {barra['acabamento']}"
                if barra.get('largura_visual'):
                    barra_desc += f" ({barra['largura_visual']})"
                visual_parts.append(barra_desc)
            
            # Textura
            if textura.get('tipo_trico_malha') and textura['tipo_trico_malha'] != 'nao_visivel':
                tex_desc = f"TEXTURA: {textura['tipo_trico_malha']}"
                if textura.get('direcao') and textura['direcao'] != 'nao_visivel':
                    tex_desc += f" - direção {textura['direcao']}"
                visual_parts.append(tex_desc)
            
            # Acabamentos especiais
            acabamentos = visual_analysis.get('acabamentos_especiais', [])
            if acabamentos:
                visual_parts.append(f"ACABAMENTOS ESPECIAIS: {', '.join(acabamentos)}")
            
            # Diferenças frente/costas
            diferencas = visual_analysis.get('diferencas_frente_costas', '')
            if diferencas and diferencas.strip():
                visual_parts.append(f"DIFERENÇAS FRENTE/COSTAS: {diferencas}")
            
            visual_description = "\n".join(visual_parts)
            
        else:
            # Legacy text format
            visual_description = str(visual_analysis)
        
        visual_section = f"""
**REFERÊNCIA VISUAL DA PEÇA (BASE OBRIGATÓRIA - SEGUIR FIELMENTE):**
{visual_description}
"""

    # Build professional prompt - ALWAYS without dimensions, POMs, or cotas
    prompt = f"""TAREFA:
Gere desenho técnico plano (flat sketch) vetorial LIMPO da peça de vestuário.
Este é um flat sketch profissional SEM DIMENSÕES (sem cotas, sem POMs).

TIPO DA PEÇA: {garment_type}

ENTRADAS:
- Material/composição: {material_info}
{material_details}
- Detalhes construtivos: {details_text}
{visual_section}

VISTAS OBRIGATÓRIAS:
- Frente e Costas (mesma escala), alinhadas VERTICALMENTE
- Manga em posição natural (quando aplicável)
- Detalhes ampliados (escala 1:2) de: gola/colarinho, punho, bolso, zíper, barra, cós, casas de botão (se aplicável)

ESTILO VISUAL:
- Fundo 100% branco (#FFFFFF); SEM corpo/manequim/cabide
- Traço preto; espessuras: 
  * Contorno: 0,75pt contínuo
  * Costuras/canelado: 0,35pt contínuo
  * Pesponto/linha de malha: 0,35pt tracejado
- Cinza 15-30% APENAS para sobreposição/forro/volume
- Simetria central indicada por linha ponto-traço (eixo central)
- Símbolos gráficos: botão (círculo 2-4mm), ilhós (anel), rebite (ponto sólido)

CORES E PADRÕES (REPRESENTAÇÃO TÉCNICA):
- Cores disponíveis: {spec.colors if spec.colors else 'não especificadas'}
- ATENÇÃO: Se a peça tiver padrão (LISTRADO, XADREZ, POÁ, ESTAMPADO, etc), REPRESENTAR graficamente usando TRAÇOS TÉCNICOS:
  * LISTRADO: desenhar linhas horizontais ou verticais paralelas (espaçamento uniforme) cobrindo TODA a área da peça
  * XADREZ: grid de linhas perpendiculares formando quadrados
  * POÁ: círculos pequenos distribuídos uniformemente
  * ESTAMPADO: indicar com padrão simplificado de formas geométricas ou orgânicas
- NÃO usar texturas fotorrealistas; apenas linhas técnicas limpas

DETALHES CONSTRUTIVOS (incluir todos aplicáveis):
- Textura/padronagem: representar com traço técnico (nervuras verticais, canelados, tranças com cruzamento claro)
- Golas/colarinho: tipo exato, altura proporcional, acabamento
- Punhos: tipo (ribana/dobrado/abotoado)
- Barras: acabamento (bainha/ribana/overlock)
- Recortes, pences, pregas, franzidos, dobras funcionais
- Fechamentos: tipo (zíper, botões, colchetes), posição e quantidade
- Casas de botão: posição centrada, quantidade
- Bolsos: tipo exato (faca, chapa, embutido, patch), tampas, vivos

NORMALIZAÇÃO:
- Corrigir perspectiva/distorções: alinhar eixo central
- Garantir simetria quando aplicável
- Remover sombras/elementos que não pertencem à construção
- Proporções visualmente balanceadas

CRITÉRIOS DE ACEITAÇÃO:
- Frente/Costas na mesma escala, perfeitamente centradas
- Eixo central indicado; simetria consistente
- Visual limpo, técnico e profissional
- SEM DIMENSÕES, SEM COTAS, SEM POMs (desenho limpo apenas)

NÃO FAZER:
- NÃO adicionar medidas ou dimensões (não solicitadas)
- NÃO incluir modelo/sombra realista/gradiente
- NÃO usar texturas fotorrealistas
- NÃO inventar detalhes não mencionados na referência visual"""

    return prompt


def convert_value_to_string(value):
    """Convert complex values (lists, dicts) to strings for database storage"""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def process_specification_with_openai(text_content):
    """Process specification text using OpenAI to extract structured data"""
    if not openai_client:
        print("OpenAI client not initialized")
        return None

    try:
        prompt = f"""Você é um especialista em análise de fichas técnicas de vestuário. Extraia TODAS as informações disponíveis do texto abaixo e retorne em formato JSON estruturado.

IMPORTANTE:
- Extraia TODOS os dados que encontrar no texto, mesmo que em formatos variados
- Se um campo não estiver explicitamente rotulado, procure a informação no contexto
- Para medidas, extraia o VALOR NUMÉRICO (ex: "64 cm" → "64 cm")
- Para datas, use formato YYYY-MM-DD quando possível
- Se uma informação NÃO estiver disponível, use null (não invente dados)

CAMPOS OBRIGATÓRIOS A EXTRAIR:

1. **Identificação da Peça:**
   - ref_souq: Código/referência da peça (pode estar como "REF", "CÓDIGO", "REFERÊNCIA")
   - description: Nome/descrição da peça (ex: "BLUSA GOLA ROLE", "VESTIDO MIDI")
   - collection: Coleção (ex: "Inverno 2025", "W26")
   - supplier: Fornecedor/fabricante
   - corner: Corner/departamento

2. **Informações Comerciais:**
   - target_price: Preço alvo/target
   - store_month: Mês de loja
   - delivery_cd_month: Mês de entrega CD

3. **Prazos e Entregas:**
   - tech_sheet_delivery_date: Data de entrega da ficha técnica
   - pilot_delivery_date: Data de entrega do piloto/protótipo
   - showcase_for: Mostruário para

4. **Equipe Envolvida:**
   - stylists: Estilistas responsáveis

5. **Matéria-Prima e Composição:**
   - composition: Composição do tecido (ex: "100% algodão", "60% poliéster 40% viscose")
   - colors: Cores disponíveis
   - tags_kit: Kit de etiquetas/aviamentos

6. **Especificações Técnicas (CRÍTICO - EXTRAIA TODOS OS VALORES):**
   - pilot_size: Tamanho piloto (ex: "P", "M", "38", "40")
   - body_length: Comprimento do corpo/total (em cm)
   - sleeve_length: Comprimento da manga (em cm)
   - hem_width: Largura da barra (em cm)
   - shoulder_to_shoulder: Largura ombro a ombro (em cm)
   - bust: Largura do busto/peito (em cm)
   - waist: Largura da cintura (em cm)
   - straight_armhole: Altura da cava (em cm)
   - neckline_depth: Profundidade do decote (em cm)
   - openings_details: Detalhes de aberturas, fechamentos, zíperes, botões
   - finishes: Acabamentos (bainhas, costuras, overlock, etc.)

7. **Design e Estilo:**
   - technical_drawing: Referência a desenho técnico se mencionado
   - reference_photos: Referências de fotos/imagens
   - specific_details: Detalhes específicos adicionais

**TEXTO DA FICHA TÉCNICA:**
{text_content}

Retorne um objeto JSON com TODOS os campos acima, usando null para informações não disponíveis."""

        # Using gpt-4o for better extraction
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role":
                "system",
                "content":
                "Você é um especialista em análise de fichas técnicas de vestuário. Extraia TODAS as informações estruturadas encontradas no texto e retorne SOMENTE em formato JSON válido, sem texto adicional. Seja preciso na extração de medidas e valores numéricos."
            }, {
                "role": "user",
                "content": prompt
            }],
            response_format={"type": "json_object"},
            max_tokens=2500)  # Increased for more comprehensive extraction

        content = response.choices[0].message.content
        if content:
            try:
                parsed_json = json.loads(content)

                # Flatten nested JSON if OpenAI grouped by categories
                flattened = {}
                for key, value in parsed_json.items():
                    if isinstance(value, dict):
                        # If value is a dict, merge its contents to top level
                        flattened.update(value)
                    else:
                        # Keep non-dict values as is
                        flattened[key] = value

                print(f"\n{'='*80}")
                print(f"DADOS EXTRAÍDOS PELO OPENAI")
                print(f"{'='*80}")
                print(f"Total de campos: {len(flattened)}")

                # Log what was extracted for debugging
                campos_importantes = [
                    'ref_souq', 'description', 'collection', 'composition',
                    'pilot_size', 'body_length', 'bust', 'sleeve_length'
                ]

                print("\n📋 CAMPOS PRINCIPAIS:")
                for key in campos_importantes:
                    value = flattened.get(key)
                    if value is not None and value != "":
                        print(f"  ✓ {key}: {str(value)}")
                    else:
                        print(f"  ✗ {key}: (vazio/não encontrado)")

                print("\n📏 OUTROS CAMPOS:")
                for key, value in flattened.items():
                    if key not in campos_importantes and value is not None and value != "":
                        print(f"  - {key}: {str(value)[:80]}...")

                print(f"{'='*80}\n")
                return flattened
            except json.JSONDecodeError as je:
                print(f"JSON parsing error: {je}")
                return None
        else:
            return None
    except Exception as e:
        print(f"Error processing with OpenAI: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_product_image(spec_id, image_b64_or_path, is_b64=True):
    """Save product image to static folder"""
    try:
        import uuid
        product_image_filename = f"product_{spec_id}_{uuid.uuid4().hex[:8]}.png"
        product_image_path = os.path.join('static', 'product_images', product_image_filename)
        
        if is_b64:
            # Decode base64 image
            import base64
            image_data = base64.b64decode(image_b64_or_path.split(',')[1] if ',' in image_b64_or_path else image_b64_or_path)
            with open(product_image_path, 'wb') as f:
                f.write(image_data)
        else:
            # Copy image file
            import shutil
            shutil.copy(image_b64_or_path, product_image_path)
        
        # Return URL path (without static/)
        return f"/static/product_images/{product_image_filename}"
    except Exception as e:
        print(f"Error saving product image: {e}")
        return None


def process_pdf_specification(spec_id, file_path):
    """Process PDF or image file and extract specification data using OpenAI"""
    try:
        spec = Specification.query.get(spec_id)
        if not spec:
            print(f"Specification {spec_id} not found")
            return
        
        filename = spec.pdf_filename
        
        # Check if it's an image or PDF
        if is_image_file(filename):
            print(f"\n{'='*80}")
            print(f"PROCESSAMENTO DE IMAGEM DETECTADO: {filename}")
            print(f"{'='*80}\n")
            
            # Save uploaded image as product image
            product_img_url = save_product_image(spec_id, file_path, is_b64=False)
            if product_img_url:
                spec.technical_drawing_url = product_img_url
                print(f"✓ Imagem do produto salva: {product_img_url}")
            
            # For images, skip text extraction and use ONLY visual analysis
            print("⚠️ Arquivo de imagem: pulando extração de texto.")
            print("📸 Usando APENAS análise visual GPT-4o para extrair informações.")
            
            # Convert image to base64 and analyze with GPT-4 Vision
            image_b64 = convert_image_to_base64(file_path)
            if not image_b64:
                print("❌ Erro ao converter imagem para base64")
                spec.processing_status = 'error'
                db.session.commit()
                return
            
            # Analyze image with GPT-4 Vision
            visual_analysis = analyze_images_with_gpt4_vision([image_b64])
            
            if not visual_analysis:
                print("❌ Erro na análise visual da imagem")
                spec.processing_status = 'error'
                db.session.commit()
                return
            
            # Extract data from visual analysis (JSON format)
            if isinstance(visual_analysis, dict):
                # Structured JSON response
                ident = visual_analysis.get('identificacao', {})
                gola = visual_analysis.get('gola_decote', {})
                mangas = visual_analysis.get('mangas', {})
                corpo = visual_analysis.get('corpo', {})
                textura = visual_analysis.get('textura_padronagem', {})
                
                # Populate spec fields from visual analysis
                tipo_peca = ident.get('tipo_peca', '')
                categoria = ident.get('categoria', '')
                
                spec.description = f"{tipo_peca}" if tipo_peca else "Peça de Vestuário (Imagem)"
                spec.composition = categoria if categoria else None
                
                # Build a descriptive summary for finishes
                detalhes = []
                if gola.get('tipo') and gola['tipo'] != 'nao_visivel':
                    detalhes.append(f"Gola: {gola['tipo']}")
                if mangas.get('comprimento') and mangas['comprimento'] != 'nao_visivel':
                    detalhes.append(f"Mangas: {mangas['comprimento']}")
                if corpo.get('comprimento_visual'):
                    detalhes.append(f"Comprimento: {corpo['comprimento_visual']}")
                
                if detalhes:
                    spec.finishes = ' | '.join(detalhes)
                
                print(f"✓ Dados extraídos da análise visual (JSON estruturado):")
                print(f"  - Descrição: {spec.description}")
                print(f"  - Categoria: {spec.composition}")
                print(f"  - Detalhes: {spec.finishes}")
            else:
                # Fallback: text response (when JSON parsing failed)
                print("⚠️ Análise visual retornou texto (fallback de JSON)")
                print("📝 Tentando extrair dados estruturados do texto com OpenAI...")
                
                # Store raw visual analysis text
                visual_text = str(visual_analysis)
                
                # Process visual text through OpenAI to extract structured data
                # This mirrors the PDF workflow for consistency
                extracted_data = process_specification_with_openai(visual_text)
                
                if extracted_data:
                    # Map extracted data to specification fields (same as PDF)
                    for key, value in extracted_data.items():
                        if hasattr(spec, key) and value is not None:
                            # Skip invalid dates
                            if key in ['tech_sheet_delivery_date', 'pilot_delivery_date']:
                                if isinstance(value, str):
                                    import re
                                    if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                                        print(f"  ⚠️ Ignorando data inválida para {key}: {value}")
                                        continue
                            # Convert lists/dicts to strings
                            setattr(spec, key, convert_value_to_string(value))
                    
                    print(f"✓ Dados extraídos via OpenAI do texto visual (fallback):")
                    print(f"  - Descrição: {spec.description}")
                    print(f"  - Composição: {spec.composition}")
                else:
                    print("⚠️ Falha ao extrair dados estruturados do texto")
                    # Last resort: try simple keyword detection
                    description_lower = visual_text.lower()
                    garment_types = {
                        'blusa': 'Blusa', 'camisa': 'Camisa', 'camiseta': 'Camiseta',
                        'vestido': 'Vestido', 'calça': 'Calça', 'short': 'Short',
                        'saia': 'Saia', 'jaqueta': 'Jaqueta', 'casaco': 'Casaco',
                        'cardigan': 'Cardigan', 'suéter': 'Suéter', 'moletom': 'Moletom'
                    }
                    
                    detected_type = None
                    for key, value in garment_types.items():
                        if key in description_lower:
                            detected_type = value
                            break
                    
                    spec.description = f"{detected_type} (Imagem)" if detected_type else "Peça de Vestuário (Imagem)"
                    spec.finishes = visual_text[:500] if len(visual_text) > 500 else visual_text
                    print(f"✓ Descrição básica extraída: {spec.description}")
            
            spec.processing_status = 'completed'
            db.session.commit()
            print(f"✓ Imagem processada com sucesso via análise visual!")
            return
            
        elif is_pdf_file(filename):
            print(f"\n{'='*80}")
            print(f"PROCESSAMENTO DE PDF DETECTADO: {filename}")
            print(f"{'='*80}\n")
            
            # Generate PDF thumbnail for preview
            thumbnail_url = generate_pdf_thumbnail(file_path, spec_id)
            if thumbnail_url:
                spec.pdf_thumbnail = thumbnail_url
                print(f"✓ Thumbnail do PDF gerado: {thumbnail_url}")
            
            # Extract images from PDF and save the first one as product image
            pdf_images = extract_images_from_pdf(file_path)
            if pdf_images and len(pdf_images) > 0:
                # Get largest image (likely the product photo, not a logo)
                largest_img = max(pdf_images, key=lambda x: x.get('area', 0))
                product_img_url = save_product_image(spec_id, largest_img['base64'], is_b64=True)
                if product_img_url:
                    spec.technical_drawing_url = product_img_url
                    print(f"✓ Imagem do produto extraída do PDF e salva: {product_img_url}")
            
            # Extract text from PDF
            text_content = extract_text_from_pdf(file_path)

            if not text_content or len(text_content.strip()) < 50:
                print(f"Insufficient text extracted from PDF for spec {spec_id}")
                spec.processing_status = 'error'
                db.session.commit()
                return

            # Process with OpenAI
            extracted_data = process_specification_with_openai(text_content)

            if not extracted_data:
                print(f"No data extracted from OpenAI for spec {spec_id}")
                spec.processing_status = 'error'
                db.session.commit()
                return

            # Map extracted data to specification fields, converting complex values
            for key, value in extracted_data.items():
                if hasattr(spec, key) and value is not None:
                    # Skip invalid dates - set to None instead of failing
                    if key in ['tech_sheet_delivery_date', 'pilot_delivery_date']:
                        # Check if it's a valid date format (YYYY-MM-DD)
                        if isinstance(value, str):
                            # If it doesn't match YYYY-MM-DD pattern, skip it
                            import re
                            if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                                print(
                                    f"  ⚠️ Ignorando data inválida para {key}: {value} (esperado YYYY-MM-DD)"
                                )
                                continue
                    # Convert lists/dicts to strings
                    setattr(spec, key, convert_value_to_string(value))

            spec.processing_status = 'completed'
            db.session.commit()
            print(f"Successfully processed PDF specification {spec_id}")
        else:
            print(f"⚠️ Formato de arquivo não reconhecido: {filename}")
            spec.processing_status = 'error'
            db.session.commit()

    except Exception as e:
        print(f"Error processing specification {spec_id}: {e}")
        import traceback
        traceback.print_exc()

        # Update status to error
        try:
            spec = Specification.query.get(spec_id)
            if spec:
                spec.processing_status = 'error'
                db.session.commit()
        except Exception as update_error:
            print(f"Error updating specification status: {update_error}")


# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            flash('Login successful!')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.')
    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('login'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))
    
    form = SettingsForm(obj=user)
    
    if form.validate_on_submit():
        # Check if username is already taken by another user
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user and existing_user.id != user.id:
            flash('Este nome de usuário já está em uso.')
            return render_template('settings.html', form=form, user=user)
        
        # Check if email is already taken by another user
        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email and existing_email.id != user.id:
            flash('Este e-mail já está em uso.')
            return render_template('settings.html', form=form, user=user)
        
        # Update user data
        user.username = form.username.data
        user.email = form.email.data
        
        try:
            db.session.commit()
            flash('Suas informações foram atualizadas com sucesso!')
            return redirect(url_for('settings'))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao atualizar suas informações. Tente novamente.')
            print(f"Error updating user: {e}")
    
    return render_template('settings.html', form=form, user=user)


@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Get filter parameters
    search_query = request.args.get('search', '').strip()
    selected_collection = request.args.get('collection', '')
    selected_supplier = request.args.get('supplier', '')
    selected_status = request.args.get('status', '')

    if user.is_admin:
        # Admin dashboard
        total_users = User.query.count()
        total_specs = Specification.query.count()
        
        # Base query for admin
        query = Specification.query
        
        # Apply filters
        if search_query:
            search_filter = f'%{search_query}%'
            query = query.filter(
                db.or_(
                    Specification.description.ilike(search_filter),
                    Specification.ref_souq.ilike(search_filter),
                    Specification.collection.ilike(search_filter),
                    Specification.pdf_filename.ilike(search_filter)
                )
            )
        
        if selected_collection:
            query = query.filter_by(collection=selected_collection)
        
        if selected_supplier:
            query = query.filter_by(supplier=selected_supplier)
        
        if selected_status:
            query = query.filter_by(status=selected_status)
        
        # Get filtered results (limit to prevent overwhelming the page)
        recent_specs = query.order_by(Specification.created_at.desc()).limit(100).all()
        
        # Get filter options
        collections = db.session.query(Specification.collection).distinct().filter(Specification.collection.isnot(None)).all()
        collections = [c[0] for c in collections if c[0]]
        
        suppliers = db.session.query(Specification.supplier).distinct().filter(Specification.supplier.isnot(None)).all()
        suppliers = [s[0] for s in suppliers if s[0]]
        
        return render_template('admin_dashboard.html',
                               current_user=user,
                               total_users=total_users,
                               total_specs=total_specs,
                               recent_specs=recent_specs,
                               collections=collections,
                               suppliers=suppliers,
                               selected_collection=selected_collection,
                               selected_supplier=selected_supplier,
                               selected_status=selected_status,
                               search_query=search_query)
    else:
        # User dashboard (stylists)
        # Base query for user
        query = Specification.query.filter_by(user_id=user.id)
        
        # Apply filters
        if search_query:
            search_filter = f'%{search_query}%'
            query = query.filter(
                db.or_(
                    Specification.description.ilike(search_filter),
                    Specification.ref_souq.ilike(search_filter),
                    Specification.collection.ilike(search_filter),
                    Specification.pdf_filename.ilike(search_filter)
                )
            )
        
        if selected_collection:
            query = query.filter_by(collection=selected_collection)
        
        if selected_supplier:
            query = query.filter_by(supplier=selected_supplier)
        
        if selected_status:
            query = query.filter_by(status=selected_status)
        
        # Get filtered results (limit to prevent overwhelming the page)
        user_specs = query.order_by(Specification.created_at.desc()).limit(100).all()
        
        # Get filter options
        collections = db.session.query(Specification.collection).distinct().filter(Specification.collection.isnot(None), Specification.user_id==user.id).all()
        collections = [c[0] for c in collections if c[0]]
        
        suppliers = db.session.query(Specification.supplier).distinct().filter(Specification.supplier.isnot(None), Specification.user_id==user.id).all()
        suppliers = [s[0] for s in suppliers if s[0]]
        
        return render_template('user_dashboard.html',
                               current_user=user,
                               specifications=user_specs,
                               collections=collections,
                               suppliers=suppliers,
                               selected_collection=selected_collection,
                               selected_supplier=selected_supplier,
                               selected_status=selected_status,
                               search_query=search_query)


@app.route('/manage_users')
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)


@app.route('/create_user', methods=['GET', 'POST'])
@admin_required
def create_user():
    form = CreateUserForm()
    if form.validate_on_submit():
        user = User()
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        user.is_admin = (form.role.data == 'admin')
        user.set_password(form.password.data)

        try:
            db.session.add(user)
            db.session.commit()
            flash(f'Usuário {user.username} criado com sucesso!')
            return redirect(url_for('manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(
                'Erro ao criar usuário. Verifique se o nome de usuário e email são únicos.'
            )

    return render_template('create_user.html', form=form)


@app.route('/suppliers')
@login_required
def suppliers():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))
    
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 5
    
    if user.is_admin:
        query = Supplier.query
    else:
        query = Supplier.query.filter_by(user_id=user.id)
    
    if search_query:
        query = query.filter(Supplier.name.ilike(f'%{search_query}%'))
    
    suppliers_paginated = query.order_by(Supplier.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    suppliers_with_counts = []
    for supplier in suppliers_paginated.items:
        spec_count = Specification.query.filter_by(supplier_id=supplier.id).count()
        suppliers_with_counts.append({
            'supplier': supplier,
            'spec_count': spec_count
        })
    
    return render_template('suppliers.html',
                         current_user=user,
                         suppliers=suppliers_with_counts,
                         pagination=suppliers_paginated,
                         search_query=search_query)


@app.route('/suppliers/create', methods=['POST'])
@login_required
def create_supplier():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'Sessão inválida'}), 401
    
    try:
        import json
        data = request.get_json()
        
        supplier = Supplier()
        supplier.user_id = user.id
        supplier.name = data.get('name')
        supplier.location = data.get('location')
        supplier.contact_name = data.get('contact_name')
        supplier.contact_email = data.get('contact_email')
        supplier.contact_phone = data.get('contact_phone')
        supplier.materials_json = json.dumps(data.get('materials', []))
        supplier.avatar_color = data.get('avatar_color', '#667eea')
        
        db.session.add(supplier)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Fornecedor criado com sucesso!', 'supplier_id': supplier.id})
    except Exception as e:
        db.session.rollback()
        print(f"Error creating supplier: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/suppliers/<int:id>', methods=['GET'])
@login_required
def get_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    
    if not user.is_admin and supplier.user_id != user.id:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403
    
    import json
    return jsonify({
        'id': supplier.id,
        'name': supplier.name,
        'location': supplier.location,
        'contact_name': supplier.contact_name,
        'contact_email': supplier.contact_email,
        'contact_phone': supplier.contact_phone,
        'materials': json.loads(supplier.materials_json) if supplier.materials_json else [],
        'avatar_color': supplier.avatar_color
    })


@app.route('/suppliers/<int:id>/update', methods=['POST'])
@login_required
def update_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    
    if not user.is_admin and supplier.user_id != user.id:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403
    
    try:
        import json
        data = request.get_json()
        
        supplier.name = data.get('name', supplier.name)
        supplier.location = data.get('location', supplier.location)
        supplier.contact_name = data.get('contact_name', supplier.contact_name)
        supplier.contact_email = data.get('contact_email', supplier.contact_email)
        supplier.contact_phone = data.get('contact_phone', supplier.contact_phone)
        supplier.materials_json = json.dumps(data.get('materials', []))
        supplier.avatar_color = data.get('avatar_color', supplier.avatar_color)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Fornecedor atualizado com sucesso!'})
    except Exception as e:
        db.session.rollback()
        print(f"Error updating supplier: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/suppliers/<int:id>/delete', methods=['POST'])
@login_required
def delete_supplier(id):
    supplier = Supplier.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    
    if not user.is_admin and supplier.user_id != user.id:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403
    
    try:
        db.session.delete(supplier)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Fornecedor excluído com sucesso!'})
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting supplier: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/upload_pdf', methods=['GET', 'POST'])
@login_required
def upload_pdf():
    form = UploadPDFForm()
    
    # Get current user to pre-fill stylist field
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))
    
    # Populate collection choices
    if user.is_admin:
        user_collections = Collection.query.order_by(Collection.name).all()
        user_suppliers = Supplier.query.order_by(Supplier.name).all()
    else:
        user_collections = Collection.query.filter_by(user_id=user.id).order_by(Collection.name).all()
        user_suppliers = Supplier.query.filter_by(user_id=user.id).order_by(Supplier.name).all()
    
    form.collection_id.choices = [(0, '-- Sem coleção --')] + [(c.id, c.name) for c in user_collections]
    form.supplier_id.choices = [(0, '-- Sem fornecedor --')] + [(s.id, s.name) for s in user_suppliers]
    
    if request.method == 'GET':
        form.stylist.data = user.username
    
    if request.method == 'POST' and form.validate_on_submit():
        try:
            file = form.pdf_file.data
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Create specification record
            spec = Specification()
            spec.user_id = session['user_id']
            spec.pdf_filename = filename
            spec.collection = form.collection.data
            spec.collection_id = form.collection_id.data if form.collection_id.data and form.collection_id.data != 0 else None
            
            # Handle supplier - save both ID and name
            if form.supplier_id.data and form.supplier_id.data != 0:
                spec.supplier_id = form.supplier_id.data
                selected_supplier = Supplier.query.get(form.supplier_id.data)
                spec.supplier = selected_supplier.name if selected_supplier else None
            else:
                spec.supplier_id = None
                spec.supplier = None
                
            spec.stylists = form.stylist.data or user.username
            spec.processing_status = 'processing'
            spec.status = 'draft'
            spec.created_at = datetime.now()

            db.session.add(spec)
            db.session.commit()

            # Process PDF asynchronously (in a real app, use Celery or similar)
            process_pdf_specification(spec.id, file_path)

            flash(
                'PDF enviado com sucesso! O processamento está em andamento.')
            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            print(f"Error in upload_pdf: {e}")
            import traceback
            traceback.print_exc()
            flash(
                'Erro ao processar o arquivo PDF. Por favor, tente novamente ou contate o suporte.'
            )
            return render_template('upload_pdf.html', form=form, current_user=user)

    return render_template('upload_pdf.html', form=form, current_user=user)


@app.route('/specification/<int:id>')
@login_required
def view_specification(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    return render_template('view_specification.html', specification=spec)


@app.route('/download_pdf/<int:id>')
@login_required
def download_pdf(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                 spec.pdf_filename)
        if os.path.exists(file_path):
            return send_file(file_path,
                             as_attachment=True,
                             download_name=spec.pdf_filename)
        else:
            flash('Arquivo PDF não encontrado.')
            return redirect(url_for('view_specification', id=id))
    except Exception as e:
        flash('Erro ao baixar o arquivo PDF.')
        return redirect(url_for('view_specification', id=id))


@app.route('/view_pdf/<int:id>')
@login_required
def view_pdf(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                 spec.pdf_filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='application/pdf')
        else:
            flash('Arquivo PDF não encontrado.')
            return redirect(url_for('view_specification', id=id))
    except Exception as e:
        flash('Erro ao visualizar o arquivo PDF.')
        return redirect(url_for('view_specification', id=id))


@app.route('/view_image/<int:id>')
@login_required
def view_image(id):
    """View uploaded image files (JPG, PNG, JPEG)"""
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                 spec.pdf_filename)
        if os.path.exists(file_path):
            # Detect mimetype based on file extension
            ext = spec.pdf_filename.lower().split('.')[-1]
            mimetype_map = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png'
            }
            mimetype = mimetype_map.get(ext, 'image/jpeg')
            return send_file(file_path, mimetype=mimetype)
        else:
            flash('Arquivo de imagem não encontrado.')
            return redirect(url_for('view_specification', id=id))
    except Exception as e:
        flash('Erro ao visualizar o arquivo de imagem.')
        return redirect(url_for('view_specification', id=id))


@app.route('/drawing/<int:id>')
@login_required
def view_drawing(id):
    """Serve the generated technical drawing image"""
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    if not spec.technical_drawing_url:
        flash('Desenho técnico não encontrado.')
        return redirect(url_for('view_specification', id=id))

    try:
        # Check if it's a legacy external URL (HTTPS) or new local filename
        if spec.technical_drawing_url.startswith(
                'http://') or spec.technical_drawing_url.startswith(
                    'https://'):
            # Legacy URL from DALL-E 3 - redirect to external URL
            return redirect(spec.technical_drawing_url)
        else:
            # Try Object Storage first
            try:
                storage_client = Client()
                if storage_client.exists(spec.technical_drawing_url):
                    image_data = storage_client.download_as_bytes(spec.technical_drawing_url)
                    return send_file(
                        io.BytesIO(image_data),
                        mimetype='image/png',
                        as_attachment=False,
                        download_name=f"desenho_{spec.id}.png"
                    )
            except Exception as storage_error:
                print(f"Object Storage lookup failed: {storage_error}")
            
            # Fallback: Try local file from GPT-Image-1
            drawing_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                        spec.technical_drawing_url)
            if os.path.exists(drawing_path):
                return send_file(drawing_path, mimetype='image/png')
            else:
                flash('Arquivo de desenho não encontrado.')
                return redirect(url_for('view_specification', id=id))
    except Exception as e:
        print(f"Error serving drawing: {e}")
        import traceback
        traceback.print_exc()
        flash('Erro ao carregar desenho técnico.')
        return redirect(url_for('view_specification', id=id))


@app.route('/specification/<int:id>/generate_drawing', methods=['POST'])
@login_required
def generate_technical_drawing(id):
    """Generate technical drawing using GPT-Image-1"""
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    if not openai_client:
        flash('OpenAI não está configurado. Contate o administrador.')
        return redirect(url_for('view_specification', id=id))

    try:
        # Get file path
        file_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                 spec.pdf_filename)
        
        # Check if it's an image or PDF
        images = []
        if is_image_file(spec.pdf_filename):
            print(f"📸 Arquivo de imagem detectado: {spec.pdf_filename}")
            # Convert image directly to base64
            image_b64 = convert_image_to_base64(file_path)
            if image_b64:
                images = [image_b64]
        elif is_pdf_file(spec.pdf_filename):
            print(f"📄 Arquivo PDF detectado: {spec.pdf_filename}")
            # Extract images from PDF (returns list of dicts with metadata)
            pdf_images_data = extract_images_from_pdf(file_path)
            # Extract only base64 strings for GPT-4 Vision
            images = [img['base64'] for img in pdf_images_data] if pdf_images_data else []
        else:
            flash('Formato de arquivo não suportado para geração de desenho.')
            return redirect(url_for('view_specification', id=id))

        # Analyze images with GPT-4 Vision to get visual description
        visual_desc = analyze_images_with_gpt4_vision(
            images) if images else None

        # Build prompt with specification data and visual description
        prompt = build_technical_drawing_prompt(spec, visual_desc)

        # Generate image using GPT-Image-1 with high quality for maximum detail
        response = openai_client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",  # GPT-Image-1 supports up to 4096x4096
            quality="high",  # High quality for better detail and precision
            n=1)

        # GPT-Image-1 returns base64 by default
        import base64
        import uuid

        # Decode the base64 image
        image_data = base64.b64decode(response.data[0].b64_json)

        # Generate unique filename
        drawing_filename = f"technical-drawings/drawing_{spec.id}_{uuid.uuid4().hex[:8]}.png"

        # Upload to Replit Object Storage
        try:
            storage_client = Client()
            storage_client.upload_from_bytes(drawing_filename, image_data)
            print(f"✅ Desenho técnico salvo no Object Storage: {drawing_filename}")
            
            # Save the Object Storage path in the database
            spec.technical_drawing_url = drawing_filename
            db.session.commit()
        except Exception as storage_error:
            print(f"❌ Erro ao fazer upload para Object Storage: {storage_error}")
            # Fallback: save locally if Object Storage fails
            local_filename = f"drawing_{spec.id}_{uuid.uuid4().hex[:8]}.png"
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], local_filename)
            with open(local_path, 'wb') as f:
                f.write(image_data)
            spec.technical_drawing_url = local_filename
            db.session.commit()
            print(f"⚠️ Fallback: Desenho salvo localmente como {local_filename}")

        flash('Desenho técnico gerado com sucesso!')
        return redirect(url_for('view_specification', id=id))

    except Exception as e:
        print(f"Error generating technical drawing: {e}")
        import traceback
        traceback.print_exc()
        flash('Erro ao gerar desenho técnico. Tente novamente.')
        return redirect(url_for('view_specification', id=id))


@app.route('/drawing/<path:filename>')
def serve_drawing(filename):
    """Serve technical drawings from Object Storage"""
    try:
        storage_client = Client()
        
        # Try to get from Object Storage first
        if storage_client.exists(filename):
            image_data = storage_client.download_as_bytes(filename)
            return send_file(
                io.BytesIO(image_data),
                mimetype='image/png',
                as_attachment=False,
                download_name=os.path.basename(filename)
            )
        
        # Fallback: try local file (for backwards compatibility)
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(local_path):
            return send_file(local_path, mimetype='image/png')
        
        # Not found anywhere
        return "Imagem não encontrada", 404
        
    except Exception as e:
        print(f"Error serving drawing {filename}: {e}")
        import traceback
        traceback.print_exc()
        
        # Last resort: try serving from local filesystem
        try:
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(local_path):
                return send_file(local_path, mimetype='image/png')
        except:
            pass
            
        return "Erro ao carregar imagem", 500


@app.route('/specification/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_specification(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    form = SpecificationForm(obj=spec)
    
    # Populate collection choices
    if user.is_admin:
        user_collections = Collection.query.order_by(Collection.name).all()
    else:
        user_collections = Collection.query.filter_by(user_id=user.id).order_by(Collection.name).all()
    
    form.collection_id.choices = [(0, '-- Sem coleção --')] + [(c.id, c.name) for c in user_collections]
    
    if form.validate_on_submit():
        # Handle collection_id specially to allow null values
        collection_id = form.collection_id.data if form.collection_id.data and form.collection_id.data != 0 else None
        form.populate_obj(spec)
        spec.collection_id = collection_id
        try:
            db.session.commit()
            flash('Especificação atualizada com sucesso!')
            return redirect(url_for('view_specification', id=spec.id))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao atualizar especificação.')

    return render_template('edit_specification.html',
                           form=form,
                           specification=spec)


@app.route('/specification/<int:id>/delete', methods=['POST'])
@login_required
def delete_specification(id):
    try:
        spec = Specification.query.get_or_404(id)
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('Sessão inválida. Por favor, faça login novamente.')
            return redirect(url_for('login'))

        # Allow access if user is admin or owns the specification
        if not user.is_admin and spec.user_id != user.id:
            flash('Acesso negado.')
            return redirect(url_for('dashboard'))

        # Delete associated file if it exists
        file_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                 spec.pdf_filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        db.session.delete(spec)
        db.session.commit()
        flash('Especificação excluída com sucesso!')
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao excluir especificação {id}: {e}")
        flash('Erro ao excluir especificação. Tente novamente.')

    return redirect(url_for('dashboard'))


@app.route('/user/<int:id>/delete', methods=['POST'])
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)

    # Don't allow deleting the current admin user
    current_user = User.query.get(session['user_id'])
    if not current_user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    if user.id == current_user.id:
        flash('Não é possível excluir seu próprio usuário.')
        return redirect(url_for('manage_users'))

    try:
        # Delete all specifications owned by this user
        Specification.query.filter_by(user_id=user.id).delete()

        db.session.delete(user)
        db.session.commit()
        flash(f'Usuário {user.username} excluído com sucesso!')
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao excluir usuário {id}: {e}")
        flash('Erro ao excluir usuário. Tente novamente.')

    return redirect(url_for('manage_users'))


@app.route('/admin/generate_thumbnails', methods=['GET'])
@admin_required
def generate_all_thumbnails():
    """Generate thumbnails for all PDFs that don't have them yet"""
    try:
        # Find all specifications with PDFs but no thumbnails
        specs = Specification.query.filter(
            Specification.pdf_filename.like('%.pdf'),
            Specification.pdf_thumbnail.is_(None)
        ).all()
        
        if not specs:
            flash('Todos os PDFs já têm thumbnails!')
            return redirect(url_for('dashboard'))
        
        processed = 0
        errors = 0
        
        for spec in specs:
            try:
                pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], spec.pdf_filename)
                
                if not os.path.exists(pdf_path):
                    print(f"PDF não encontrado: {pdf_path}")
                    errors += 1
                    continue
                
                thumbnail_url = generate_pdf_thumbnail(pdf_path, spec.id)
                if thumbnail_url:
                    spec.pdf_thumbnail = thumbnail_url
                    db.session.commit()
                    processed += 1
                    print(f"✓ Thumbnail gerado para spec #{spec.id}: {thumbnail_url}")
                else:
                    errors += 1
                    print(f"✗ Erro ao gerar thumbnail para spec #{spec.id}")
                    
            except Exception as e:
                errors += 1
                print(f"✗ Erro ao processar spec #{spec.id}: {e}")
                continue
        
        if processed > 0:
            flash(f'✓ {processed} thumbnails gerados com sucesso! ({errors} erros)')
        else:
            flash(f'Nenhum thumbnail foi gerado. ({errors} erros)')
            
    except Exception as e:
        flash(f'Erro ao gerar thumbnails: {str(e)}')
        print(f"Erro ao gerar thumbnails: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('dashboard'))


# Collections Routes
@app.route('/collections')
@login_required
def collections():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))
    
    # Get user's collections
    if user.is_admin:
        user_collections = Collection.query.order_by(Collection.created_at.desc()).all()
    else:
        user_collections = Collection.query.filter_by(user_id=user.id).order_by(Collection.created_at.desc()).all()
    
    return render_template('collections.html',
                           current_user=user,
                           collections=user_collections)


@app.route('/create_collection', methods=['POST'])
@login_required
def create_collection():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))
    
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    status = request.form.get('status', 'em_desenvolvimento')
    
    if not name:
        flash('Nome da coleção é obrigatório!')
        return redirect(url_for('collections'))
    
    cover_image_path = None
    
    if 'cover_image' in request.files:
        cover_image = request.files['cover_image']
        if cover_image and cover_image.filename:
            filename = secure_filename(cover_image.filename)
            
            if filename:
                ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                
                if ext in ['jpg', 'jpeg', 'png']:
                    import hashlib
                    import time
                    
                    unique_name = f"collection_{int(time.time())}_{hashlib.md5(filename.encode()).hexdigest()[:8]}.{ext}"
                    
                    covers_dir = os.path.join('static', 'covers')
                    os.makedirs(covers_dir, exist_ok=True)
                    
                    filepath = os.path.join(covers_dir, unique_name)
                    cover_image.save(filepath)
                    
                    cover_image_path = f"covers/{unique_name}"
                else:
                    flash('Formato de imagem inválido. Use JPG, JPEG ou PNG.')
    
    try:
        new_collection = Collection(
            user_id=user.id,
            name=name,
            description=description,
            status=status,
            cover_image=cover_image_path
        )
        db.session.add(new_collection)
        db.session.commit()
        flash(f'Coleção "{name}" criada com sucesso!')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao criar coleção: {str(e)}')
        print(f"Erro ao criar coleção: {e}")
    
    return redirect(url_for('collections'))


@app.route('/collection/<int:id>')
@login_required
def view_collection(id):
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))
    
    collection = Collection.query.get_or_404(id)
    
    # Check access permissions
    if not user.is_admin and collection.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('collections'))
    
    # Get specifications in this collection
    specs = Specification.query.filter_by(collection_id=id).order_by(Specification.created_at.desc()).all()
    
    return render_template('view_collection.html',
                           current_user=user,
                           collection=collection,
                           specifications=specs)


@app.route('/collection/<int:id>/edit', methods=['POST'])
@login_required
def edit_collection(id):
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))
    
    collection = Collection.query.get_or_404(id)
    
    # Check access permissions
    if not user.is_admin and collection.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('collections'))
    
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    status = request.form.get('status', 'em_desenvolvimento')
    
    if not name:
        flash('Nome da coleção é obrigatório!')
        return redirect(url_for('collections'))
    
    # Handle cover image upload
    if 'cover_image' in request.files:
        cover_image = request.files['cover_image']
        if cover_image and cover_image.filename:
            filename = secure_filename(cover_image.filename)
            
            if filename:
                ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                
                if ext in ['jpg', 'jpeg', 'png']:
                    import hashlib
                    import time
                    
                    # Delete old cover image if exists
                    if collection.cover_image:
                        old_image_path = os.path.join('static', collection.cover_image)
                        if os.path.exists(old_image_path):
                            try:
                                os.remove(old_image_path)
                            except Exception as e:
                                print(f"Erro ao remover imagem antiga: {e}")
                    
                    # Save new image
                    unique_name = f"collection_{int(time.time())}_{hashlib.md5(filename.encode()).hexdigest()[:8]}.{ext}"
                    
                    covers_dir = os.path.join('static', 'covers')
                    os.makedirs(covers_dir, exist_ok=True)
                    
                    filepath = os.path.join(covers_dir, unique_name)
                    cover_image.save(filepath)
                    
                    collection.cover_image = f"covers/{unique_name}"
                else:
                    flash('Formato de imagem inválido. Use JPG, JPEG ou PNG.')
    
    try:
        collection.name = name
        collection.description = description
        collection.status = status
        
        db.session.commit()
        flash(f'Coleção "{name}" atualizada com sucesso!')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao atualizar coleção: {str(e)}')
        print(f"Erro ao atualizar coleção: {e}")
    
    return redirect(url_for('collections'))


@app.route('/technical-drawings')
@login_required
def technical_drawings():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    # Base query: only specifications with technical drawings
    if user.is_admin:
        query = Specification.query.filter(Specification.technical_drawing_url.isnot(None))
    else:
        query = Specification.query.filter(
            Specification.user_id == user.id,
            Specification.technical_drawing_url.isnot(None)
        )
    
    # Search filter
    search = request.args.get('search', '').strip()
    if search:
        query = query.filter(
            db.or_(
                Specification.description.ilike(f'%{search}%'),
                Specification.ref_souq.ilike(f'%{search}%'),
                Specification.collection.ilike(f'%{search}%')
            )
        )
    
    # Collection filter
    collection_filter = request.args.get('collection', '').strip()
    if collection_filter:
        query = query.filter(Specification.collection_id == collection_filter)
    
    # Supplier filter
    supplier_filter = request.args.get('supplier', '').strip()
    if supplier_filter:
        query = query.filter(Specification.supplier.ilike(f'%{supplier_filter}%'))
    
    # Get all collections for filter dropdown
    if user.is_admin:
        all_collections = Collection.query.order_by(Collection.name).all()
    else:
        all_collections = Collection.query.filter_by(user_id=user.id).order_by(Collection.name).all()
    
    # Get unique suppliers for filter dropdown
    if user.is_admin:
        suppliers_query = db.session.query(Specification.supplier).filter(
            Specification.supplier.isnot(None),
            Specification.supplier != '',
            Specification.technical_drawing_url.isnot(None)
        ).distinct().order_by(Specification.supplier)
    else:
        suppliers_query = db.session.query(Specification.supplier).filter(
            Specification.user_id == user.id,
            Specification.supplier.isnot(None),
            Specification.supplier != '',
            Specification.technical_drawing_url.isnot(None)
        ).distinct().order_by(Specification.supplier)
    
    all_suppliers = [s[0] for s in suppliers_query.all()]
    
    # Paginate results
    pagination = query.order_by(Specification.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    return render_template('technical_drawings.html',
                           current_user=user,
                           specifications=pagination.items,
                           pagination=pagination,
                           collections=all_collections,
                           suppliers=all_suppliers,
                           search=search,
                           selected_collection=collection_filter,
                           selected_supplier=supplier_filter)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create admin user if it doesn't exist
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: username='admin', password='admin123'")

    app.run(host='0.0.0.0', port=5000, debug=True)
