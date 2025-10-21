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
import pymupdf as fitz  # PyMuPDF
import requests

# Import OpenAI functionality
from openai import OpenAI

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET')
if not app.config['SECRET_KEY']:
    raise RuntimeError("SESSION_SECRET environment variable is required")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Verifica conexões antes de usar
    'pool_recycle': 3600,   # Reconecta a cada hora
    'pool_timeout': 30,     # Timeout de 30 segundos para conexões
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

# Custom Jinja filter to parse JSON
@app.template_filter('from_json')
def from_json_filter(value):
    if value:
        try:
            return json.loads(value)
        except:
            return {}
    return {}

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with specifications
    specifications = db.relationship('Specification', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Specification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
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
    
    # Raw extracted text and status
    raw_extracted_text = db.Column(db.Text)
    processing_status = db.Column(db.String(50), default='pending')  # pending, processing, completed, error
    
    # New: Structured measurements and technical drawing generation
    measurements_json = db.Column(db.Text)  # JSON with structured measurements (Prompt 2 format)
    size_scale_json = db.Column(db.Text)  # JSON array of size scale (e.g., ["PP","P","M","G","GG"])
    measurement_base_size = db.Column(db.String(50))  # Base/pilot size (e.g., "M", "38")
    tolerances_json = db.Column(db.Text)  # JSON with tolerances per measurement
    measurements_status = db.Column(db.String(50), default='pending')  # pending, processing, completed, error
    
    # Image extraction and generation
    reference_image_path = db.Column(db.String(255))  # Best reference image extracted from PDF
    has_technical_sketch = db.Column(db.Boolean, default=False)  # Does PDF already have a technical sketch?
    generated_front_image = db.Column(db.String(255))  # Path to generated front view
    generated_back_image = db.Column(db.String(255))  # Path to generated back view
    sketch_generation_status = db.Column(db.String(50), default='pending')  # pending, processing, completed, error, not_needed

# Forms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    is_admin = SelectField('Role', choices=[('0', 'User'), ('1', 'Admin')], coerce=int)
    submit = SubmitField('Create User')

class UploadPDFForm(FlaskForm):
    pdf_file = FileField('PDF File', validators=[
        FileRequired(),
        FileAllowed(['pdf'], 'PDF files only!')
    ])
    submit = SubmitField('Upload and Process')

class SpecificationForm(FlaskForm):
    # 1. Identificação da Peça
    ref_souq = StringField('Referência (REF SOUQ)')
    description = TextAreaField('Descrição')
    collection = StringField('Coleção')
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

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
    return text

def extract_images_from_pdf(pdf_path, output_dir='uploads/generated'):
    """Extract images from PDF file using PyMuPDF. Returns list of image paths sorted by quality."""
    images = []
    try:
        pdf_document = fitz.open(pdf_path)
        
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            image_list = page.get_images(full=True)
            
            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Save image
                image_filename = f"page{page_num + 1}_img{img_index + 1}.{image_ext}"
                image_path = os.path.join(output_dir, image_filename)
                
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)
                
                # Store image info with size (for quality ranking)
                images.append({
                    'path': image_path,
                    'size': len(image_bytes),
                    'page': page_num + 1,
                    'ext': image_ext
                })
        
        pdf_document.close()
        
        # Sort by size (larger images usually better quality)
        images.sort(key=lambda x: x['size'], reverse=True)
        
    except Exception as e:
        print(f"Error extracting images from PDF: {e}")
    
    return images

def extract_measurements_with_vision(text_content, image_paths=None):
    """Extract structured measurements using OpenAI Vision (Prompt 2 format)"""
    if not openai_client:
        print("OpenAI client not initialized")
        return None
    
    try:
        # Build the prompt based on Prompt 2
        prompt = """Extraia APENAS as MEDIDAS da peça e retorne um JSON exatamente neste esquema. 
- Unidade: cm
- Use ponto decimal
- Não invente valores: ausentes = null
- Se houver só tamanho base, preencha somente ele

ESQUEMA_JSON:
{
  "unidade": "cm",
  "escala_tamanhos": ["PP","P","M","G","GG"],
  "tamanho_base": "M",
  "tabela": {
    "frente": {
      "comprimento_corpo": { "PP": null, "P": null, "M": null, "G": null, "GG": null },
      "comprimento_manga": { "PP": null, "P": null, "M": null, "G": null, "GG": null },
      "busto": { "PP": null, "P": null, "M": null, "G": null, "GG": null },
      "cintura": { "PP": null, "P": null, "M": null, "G": null, "GG": null },
      "barra": { "PP": null, "P": null, "M": null, "G": null, "GG": null },
      "ombro_a_ombro": { "PP": null, "P": null, "M": null, "G": null, "GG": null },
      "cava_reta": { "PP": null, "P": null, "M": null, "G": null, "GG": null },
      "gola_altura": { "PP": null, "P": null, "M": null, "G": null, "GG": null }
    },
    "costas": {}
  },
  "tolerancias": { "comprimento_corpo": 1.0, "comprimento_manga": 1.0, "larguras": 0.5 },
  "observacoes_medidas": null
}

Sinônimos úteis: busto~peito/torax | cintura~waist | barra~hem | ombro a ombro~ombro | cava reta~armhole | comprimento corpo~comprimento total | comprimento manga~manga longa/curta | gola_altura~altura da gola/rolê.

TEXTO DAS MEDIDAS:
""" + text_content
        
        messages = [
            {
                "role": "system",
                "content": "Você é um agente especializado em fichas técnicas de moda. Extraia APENAS medidas em formato JSON válido, números em cm (float), valores ausentes = null."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        
        # If we have images, add them to the message (Vision mode)
        if image_paths and len(image_paths) > 0:
            # Use the best image (first one, already sorted by quality)
            best_image_path = image_paths[0]['path']
            
            with open(best_image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
                
            # Determine image type
            ext = image_paths[0]['ext'].lower()
            if ext == 'jpg' or ext == 'jpeg':
                mime_type = 'image/jpeg'
            elif ext == 'png':
                mime_type = 'image/png'
            else:
                mime_type = 'image/jpeg'  # default
            
            # Add image to the message
            messages[1]["content"].append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_data}"
                }
            })
        
        # Call OpenAI with Vision support
        response = openai_client.chat.completions.create(
            model="gpt-4o",  # gpt-4o has vision support and JSON mode
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=2000
        )
        
        content = response.choices[0].message.content
        if content:
            try:
                parsed_json = json.loads(content)
                return parsed_json
            except json.JSONDecodeError as je:
                print(f"JSON parsing error in measurements extraction: {je}")
                return None
        else:
            return None
            
    except Exception as e:
        print(f"Error extracting measurements with vision: {e}")
        return None

def detect_technical_sketch(image_paths):
    """Detect if PDF contains a technical flat sketch using OpenAI Vision"""
    if not openai_client or not image_paths or len(image_paths) == 0:
        return False
    
    try:
        # Check each image to see if it's a technical sketch
        for img_info in image_paths:
            image_path = img_info['path']
            
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            ext = img_info['ext'].lower()
            if ext == 'jpg' or ext == 'jpeg':
                mime_type = 'image/jpeg'
            elif ext == 'png':
                mime_type = 'image/png'
            else:
                mime_type = 'image/jpeg'
            
            messages = [
                {
                    "role": "system",
                    "content": "Você é um especialista em design técnico de moda. Responda apenas 'SIM' ou 'NÃO'."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Esta imagem é um CROQUI TÉCNICO (flat sketch) de vestuário? Características: line art, fundo branco ou transparente, traço preto/cinza, peça isolada sem modelo, aparência vetorial, detalhes de costura visíveis. Responda apenas SIM ou NÃO."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            }
                        }
                    ]
                }
            ]
            
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=10
            )
            
            answer = response.choices[0].message.content.strip().upper()
            if "SIM" in answer or "YES" in answer:
                return True
        
        return False
        
    except Exception as e:
        print(f"Error detecting technical sketch: {e}")
        return False

def generate_technical_drawing(reference_image_path, measurements_json, spec_id, output_dir='uploads/generated'):
    """Generate technical flat sketch using DALL-E-3 (Prompt 3 format)"""
    if not openai_client:
        print("OpenAI client not initialized")
        return None, None
    
    try:
        # Build measurements block from tamanho_base
        measurements_block = ""
        if measurements_json:
            tamanho_base = measurements_json.get('tamanho_base', 'M')
            tabela_frente = measurements_json.get('tabela', {}).get('frente', {})
            
            measurements_block = f"\nTamanho base: {tamanho_base} (cm)\n"
            for medida, valores in tabela_frente.items():
                if isinstance(valores, dict) and tamanho_base in valores:
                    valor = valores[tamanho_base]
                    if valor is not None:
                        measurements_block += f"- {medida}: {valor}\n"
        
        # Build Prompt 3
        prompt = f"""Transforme esta imagem de roupa em um DESENHO TÉCNICO PLANO (flat sketch) fiel às medidas e detalhes de construção.

REQUISITOS DE ESTILO (obrigatórios):
- Estilo técnico (line art), aparência vetorial
- Fundo totalmente branco
- Traço preto contínuo e regular
- Peça isolada (sem modelo/manequim)
- Simetria central
- Sombra mínima (flat 2D)
- Permita escala de cinza leve somente para indicar sobreposição

DETALHES DE CONSTRUÇÃO A INCLUIR:
- Linhas de costura e pespontos
- Recortes e pences
- Golas, punhos, barras e acabamentos
- Fechamentos (zíper, botão, amarração etc.)
- Pregas, franzidos, dobras e sobreposições quando presentes

RESTRIÇÕES DE MEDIDAS (cm) — ajustar proporções para respeitar:{measurements_block}

INSTRUÇÕES ADICIONAIS:
- Não desenhar números/cotas sobre a arte final.
- Gerar vista frontal detalhada.
Saída desejada: desenho técnico plano detalhado, pronto para ficha técnica."""
        
        # Read reference image and convert to base64
        with open(reference_image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Determine image type
        ext = os.path.splitext(reference_image_path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            mime_type = 'image/jpeg'
        elif ext == '.png':
            mime_type = 'image/png'
        else:
            mime_type = 'image/jpeg'
        
        # Generate front view with DALL-E-3
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        
        front_image_url = response.data[0].url
        
        # Download and save front image
        front_filename = f"spec_{spec_id}_front.png"
        front_path = os.path.join(output_dir, front_filename)
        
        img_response = requests.get(front_image_url)
        with open(front_path, 'wb') as f:
            f.write(img_response.content)
        
        # Try to generate back view
        back_path = None
        try:
            back_prompt = prompt.replace("vista frontal", "vista posterior (costas)")
            
            back_response = openai_client.images.generate(
                model="dall-e-3",
                prompt=back_prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            
            back_image_url = back_response.data[0].url
            back_filename = f"spec_{spec_id}_back.png"
            back_path = os.path.join(output_dir, back_filename)
            
            back_img_response = requests.get(back_image_url)
            with open(back_path, 'wb') as f:
                f.write(back_img_response.content)
        except Exception as e:
            print(f"Could not generate back view: {e}")
        
        return front_path, back_path
        
    except Exception as e:
        print(f"Error generating technical drawing: {e}")
        return None, None

def process_specification_with_openai(text_content):
    """Process specification text using OpenAI to extract structured data"""
    if not openai_client:
        print("OpenAI client not initialized")
        return None
    
    try:
        prompt = """
        Analise o seguinte texto de ficha técnica de vestuário e extraia as informações estruturadas em formato JSON.
        
        Extraia as seguintes categorias:
        1. Identificação da Peça: ref_souq, description, collection, supplier, corner
        2. Informações Comerciais: target_price, store_month, delivery_cd_month
        3. Prazos e Entregas: tech_sheet_delivery_date, pilot_delivery_date, showcase_for
        4. Equipe Envolvida: stylists
        5. Matéria-Prima e Aviamentos: composition, colors, tags_kit
        6. Especificações Técnicas: pilot_size, body_length, sleeve_length, hem_width, shoulder_to_shoulder, bust, waist, straight_armhole, neckline_depth, openings_details, finishes
        7. Design e Estilo: technical_drawing, reference_photos, specific_details
        
        Para datas, use formato YYYY-MM-DD. Se uma informação não estiver disponível, use null.
        
        Texto da ficha técnica:
        """ + text_content
        
        # Using gpt-4-turbo for JSON mode support
        response = openai_client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Você é um especialista em análise de fichas técnicas de vestuário. Extraia informações estruturadas e retorne SOMENTE em formato JSON válido, sem texto adicional."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=2000
        )
        
        
        content = response.choices[0].message.content
        if content:
            try:
                parsed_json = json.loads(content)
                return parsed_json
            except json.JSONDecodeError as je:
                print(f"JSON parsing error: {je}")
                return None
        else:
            return None
    except Exception as e:
        print(f"Error processing with OpenAI: {e}")
        return None

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

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    if user.is_admin:
        # Admin dashboard
        total_users = User.query.count()
        total_specs = Specification.query.count()
        recent_specs = Specification.query.order_by(Specification.created_at.desc()).limit(10).all()
        return render_template('admin_dashboard.html', 
                             total_users=total_users, 
                             total_specs=total_specs, 
                             recent_specs=recent_specs)
    else:
        # User dashboard
        user_specs = Specification.query.filter_by(user_id=user.id).order_by(Specification.created_at.desc()).all()
        return render_template('user_dashboard.html', specifications=user_specs)

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
        user.is_admin = bool(form.is_admin.data)
        user.set_password(form.password.data)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash(f'Usuário {user.username} criado com sucesso!')
            return redirect(url_for('manage_users'))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao criar usuário. Verifique se o nome de usuário e email são únicos.')
    
    return render_template('create_user.html', form=form)

@app.route('/upload_pdf', methods=['GET', 'POST'])
@login_required
def upload_pdf():
    form = UploadPDFForm()
    if request.method == 'POST' and form.validate_on_submit():
        file = form.pdf_file.data
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Create specification record
        spec = Specification()
        spec.user_id = session['user_id']
        spec.pdf_filename = filename
        spec.processing_status = 'processing'
        spec.created_at = datetime.now()
        
        try:
            db.session.add(spec)
            db.session.commit()
            
            # Process PDF asynchronously (in a real app, use Celery or similar)
            process_pdf_specification(spec.id, file_path)
            
            flash('PDF enviado com sucesso! O processamento está em andamento.')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao processar o arquivo PDF.')
    
    return render_template('upload_pdf.html', form=form)

@app.route('/specification/<int:id>')
@login_required
def view_specification(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    
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
    
    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))
    
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], spec.pdf_filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=spec.pdf_filename)
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
    
    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))
    
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], spec.pdf_filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='application/pdf')
        else:
            flash('Arquivo PDF não encontrado.')
            return redirect(url_for('view_specification', id=id))
    except Exception as e:
        flash('Erro ao visualizar o arquivo PDF.')
        return redirect(url_for('view_specification', id=id))

@app.route('/generated/<path:filename>')
@login_required
def serve_generated_image(filename):
    """Serve generated technical drawings"""
    try:
        file_path = os.path.join('uploads/generated', filename)
        if os.path.exists(file_path):
            return send_file(file_path)
        else:
            return "Imagem não encontrada", 404
    except Exception as e:
        print(f"Error serving generated image: {e}")
        return "Erro ao carregar imagem", 500

@app.route('/specification/<int:id>/regenerate_sketch', methods=['POST'])
@login_required
def regenerate_sketch(id):
    """Manually regenerate technical drawing"""
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    
    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))
    
    try:
        # Check if we have measurements and reference image
        if not spec.measurements_json:
            flash('Não é possível gerar desenho sem medidas extraídas.')
            return redirect(url_for('view_specification', id=id))
        
        if not spec.reference_image_path or not os.path.exists(spec.reference_image_path):
            flash('Não é possível gerar desenho sem imagem de referência.')
            return redirect(url_for('view_specification', id=id))
        
        # Parse measurements
        measurements_data = json.loads(spec.measurements_json)
        
        # Generate technical drawing
        spec.sketch_generation_status = 'processing'
        db.session.commit()
        
        front_path, back_path = generate_technical_drawing(
            reference_image_path=spec.reference_image_path,
            measurements_json=measurements_data,
            spec_id=spec.id,
            output_dir=f'uploads/generated/spec_{spec.id}'
        )
        
        if front_path:
            spec.generated_front_image = front_path
        if back_path:
            spec.generated_back_image = back_path
        
        spec.sketch_generation_status = 'completed' if front_path else 'error'
        db.session.commit()
        
        if front_path:
            flash('Desenho técnico gerado com sucesso!')
        else:
            flash('Erro ao gerar desenho técnico.')
            
    except Exception as e:
        print(f"Error regenerating sketch: {e}")
        spec.sketch_generation_status = 'error'
        db.session.commit()
        flash('Erro ao gerar desenho técnico.')
    
    return redirect(url_for('view_specification', id=id))

@app.route('/specification/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_specification(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    
    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))
    
    form = SpecificationForm(obj=spec)
    if form.validate_on_submit():
        form.populate_obj(spec)
        try:
            db.session.commit()
            flash('Especificação atualizada com sucesso!')
            return redirect(url_for('view_specification', id=spec.id))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao atualizar especificação.')
    
    return render_template('edit_specification.html', form=form, specification=spec)

@app.route('/specification/<int:id>/delete', methods=['POST'])
@login_required
def delete_specification(id):
    try:
        spec = Specification.query.get_or_404(id)
        user = User.query.get(session['user_id'])
        
        # Allow access if user is admin or owns the specification
        if not user.is_admin and spec.user_id != user.id:
            flash('Acesso negado.')
            return redirect(url_for('dashboard'))
        
        # Delete associated file if it exists
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], spec.pdf_filename)
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
    if user.id == current_user.id:
        flash('Não é possível excluir seu próprio usuário.')
        return redirect(url_for('manage_users'))
    
    try:
        # Delete all user specifications and files
        for spec in user.specifications:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], spec.pdf_filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        db.session.delete(user)
        db.session.commit()
        flash(f'Usuário {user.username} excluído com sucesso!')
    except Exception as e:
        db.session.rollback()
        flash('Erro ao excluir usuário.')
    
    return redirect(url_for('manage_users'))

def process_pdf_specification(spec_id, file_path):
    """Process PDF specification with measurements extraction and technical drawing generation"""
    try:
        spec = Specification.query.get(spec_id)
        if not spec:
            return
        
        # STEP 1: Extract text from PDF
        text_content = extract_text_from_pdf(file_path)
        spec.raw_extracted_text = text_content
        
        if not text_content.strip():
            spec.processing_status = 'error'
            spec.measurements_status = 'error'
            db.session.commit()
            return
        
        # STEP 2: Process general data with OpenAI (original functionality)
        extracted_data = process_specification_with_openai(text_content)
        
        if extracted_data:
            # Update specification with extracted data
            for category, fields in extracted_data.items():
                if isinstance(fields, dict):
                    for field, value in fields.items():
                        if hasattr(spec, field) and value:
                            setattr(spec, field, value)
            
            spec.processing_status = 'completed'
        else:
            spec.processing_status = 'error'
        
        db.session.commit()
        
        # STEP 3: Extract images from PDF
        print(f"Extracting images from PDF for spec {spec_id}...")
        images = extract_images_from_pdf(file_path, output_dir=f'uploads/generated/spec_{spec_id}')
        os.makedirs(f'uploads/generated/spec_{spec_id}', exist_ok=True)
        
        # STEP 4: Extract structured measurements with Vision
        spec.measurements_status = 'processing'
        db.session.commit()
        
        print(f"Extracting measurements with Vision for spec {spec_id}...")
        measurements_data = extract_measurements_with_vision(text_content, images)
        
        if measurements_data:
            # Store measurements JSON
            spec.measurements_json = json.dumps(measurements_data, ensure_ascii=False)
            spec.size_scale_json = json.dumps(measurements_data.get('escala_tamanhos', []))
            spec.measurement_base_size = measurements_data.get('tamanho_base', 'M')
            spec.tolerances_json = json.dumps(measurements_data.get('tolerancias', {}))
            spec.measurements_status = 'completed'
            print(f"Measurements extracted successfully for spec {spec_id}")
        else:
            spec.measurements_status = 'error'
            print(f"Failed to extract measurements for spec {spec_id}")
        
        db.session.commit()
        
        # STEP 5: Detect if PDF has technical sketch
        if images and len(images) > 0:
            print(f"Detecting technical sketch for spec {spec_id}...")
            has_sketch = detect_technical_sketch(images)
            spec.has_technical_sketch = has_sketch
            
            # Save best reference image
            if images:
                spec.reference_image_path = images[0]['path']
            
            db.session.commit()
            print(f"Technical sketch detected: {has_sketch}")
        else:
            spec.has_technical_sketch = False
            db.session.commit()
            print(f"No images found in PDF for spec {spec_id}")
        
        # STEP 6: Generate technical drawing if needed
        if not spec.has_technical_sketch and images and len(images) > 0 and measurements_data:
            print(f"Generating technical drawing for spec {spec_id}...")
            spec.sketch_generation_status = 'processing'
            db.session.commit()
            
            front_path, back_path = generate_technical_drawing(
                reference_image_path=images[0]['path'],
                measurements_json=measurements_data,
                spec_id=spec_id,
                output_dir=f'uploads/generated/spec_{spec_id}'
            )
            
            if front_path:
                spec.generated_front_image = front_path
                print(f"Front view generated: {front_path}")
            if back_path:
                spec.generated_back_image = back_path
                print(f"Back view generated: {back_path}")
            
            spec.sketch_generation_status = 'completed' if front_path else 'error'
            db.session.commit()
        else:
            spec.sketch_generation_status = 'not_needed' if spec.has_technical_sketch else 'pending'
            db.session.commit()
            
        print(f"Processing completed for spec {spec_id}")
        
    except Exception as e:
        print(f"Error processing PDF specification {spec_id}: {e}")
        import traceback
        traceback.print_exc()
        spec = Specification.query.get(spec_id)
        if spec:
            spec.processing_status = 'error'
            spec.measurements_status = 'error'
            spec.sketch_generation_status = 'error'
            db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create default admin user if none exists
        if not User.query.filter_by(is_admin=True).first():
            admin = User()
            admin.username = 'admin'
            admin.email = 'admin@example.com'
            admin.is_admin = True
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
    
    app.run(host='0.0.0.0', port=5000, debug=True)