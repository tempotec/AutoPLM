# Overview

This Flask-based platform manages technical specifications for the fashion/textile industry. It processes PDF and image files (JPG, PNG, JPEG) to extract technical data using OpenAI's API. A key feature is AI-powered generation of clean, professional flat sketches based on extracted specifications and visual analysis of garment images. The system includes role-based access control and comprehensive activity tracking. The platform's ambition is to streamline the technical design process in the fashion industry by automating data extraction and technical drawing creation.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## UI/UX Decisions
- **Frontend**: Jinja2 templates, Bootstrap 5 for responsive design.
- **Styling**: Custom CSS, Font Awesome icons.
- **Forms**: Flask-WTF for secure handling, CSRF protection.
- **File Upload**: Drag-and-drop interface with client-side validation.
- **Localization**: User interface is 100% in Brazilian Portuguese.
- **Design Theme**: Professional dark theme applied consistently across all templates.
- **Branding**: Custom logo (PDF with gear icon) displayed across all pages at 32px height in sidebar and login page.
- **Image Display**: Dashboard cards display PDF preview thumbnails, technical drawings, or product images with proper styling and fallbacks.
- **Navigation**: Professional sidebar with key sections and user profile display.

## Technical Implementations
- **Web Framework**: Flask with a modular route structure.
- **Database ORM**: SQLAlchemy for database abstraction with thread-safe session management.
- **Authentication**: Session-based, with Werkzeug for password hashing and role-based access control (admin, stylist).
- **File Processing**: PyPDF2 for PDF text and image extraction; PyMuPDF for PDF thumbnail generation.
- **AI Processing**: OpenAI API for data parsing, vision analysis, and image generation.
- **Asynchronous Processing**: Background threading for PDF/image processing with dedicated database sessions, allowing users to navigate freely while files process.
- **Real-time Notifications**: Toast notification system (toast.js) with AJAX polling for processing status updates.
- **Data Storage**: SQL database for primary data. Replit Object Storage for technical drawings, with local filesystem fallback.
- **Security**: CSRF protection, secure filename handling, file size limits.

## System Design Choices
- **Data Model**: Includes Specifications, Collections, Suppliers, and relationships between them. Suppliers can be linked to specifications for better tracking of manufacturing partners.
- **AI Integration Workflow** (totalmente assíncrono em background):
    1. **Upload de Arquivo**: PDF/Image upload retorna imediatamente, processamento em thread separada.
    2. **Extração de Dados**: Análise de texto (GPT-4-Turbo) e extração de imagens (PyPDF2) em background.
    3. **Análise Visual**: GPT-4o Vision analisa imagens para produzir JSON estruturado com detalhes de construção.
    4. **Geração de Desenho Técnico (Image-to-Image)**: Usuário clica em "Gerar Desenho Técnico", requisição retorna instantaneamente. GPT-Image-1 usa `images.edit()` recebendo a imagem original como base + prompt técnico, transformando a foto/ilustração real em desenho técnico plano. Isso preserva proporções, detalhes construtivos, e características da peça original (golas, bolsos, recortes, listras), resultando em desenhos muito mais fiéis. Fallback para `images.generate()` (text-to-image) se nenhuma imagem base for encontrada.
    5. **Notificações em Tempo Real**: Sistema de toast mostra "Processando..." com polling automático do status.
    6. **Armazenamento**: Object Storage para desenhos gerados, com fallback para sistema de arquivos local.
- **Feature Set**:
    - **Asynchronous File Upload & Drawing Generation**: Files and technical drawings are processed in background threads while users can navigate freely. Real-time status updates via AJAX polling with toast notifications showing "Processando", "Completo", or "Erro" states. Users never experience blocked UI - all AI operations happen asynchronously.
    - **Data Extraction**: Transforms unstructured PDF content into structured records (product identification, commercial info, deadlines, materials, technical measurements).
    - **AI-Powered Categorization**: Automatic classification of garments into Grupo (TECIDO PLANO, MALHA, TRICOT, JEANS) and Subgrupo (BLAZER, BLUSA, CALÇA, etc.) using GPT-4o Vision and GPT-4 Text analysis. Fields are auto-filled during creation and remain editable by users.
    - **Pattern/Print Extraction**: Automatic extraction of fabric pattern/print information (Listrado, Floral, Xadrez, Liso, Poá, etc.) using GPT-4o Vision for images and GPT-4 for PDFs. Extracted pattern is displayed separately from composition and is fully editable by users.
    - **Manual Price Range Classification (P1-P4)**: Stylist-defined price range field with manual selection during upload and editing. Not AI-generated - allows stylists to classify garments into one of four price tiers (P1, P2, P3, P4) with color-coded badges and filtering capabilities.
    - **Auto-Registration of Suppliers**: When processing PDFs/images, the system automatically extracts supplier names and creates supplier records if they don't exist. Suppliers are matched case-insensitively to avoid duplicates, then linked to specifications.
    - **Technical Drawing Generation (Image-to-Image)**: Produces professional flat sketches using GPT-Image-1's `images.edit()` method. The system extracts the original garment image (from uploaded image files or largest image in PDFs) and passes it as a visual base alongside the technical prompt. This image-to-image approach preserves the actual proportions, construction details, and design elements of the original piece, resulting in technical drawings that accurately reflect the garment's real appearance. Automatic fallback to text-to-image generation if no base image is available.
    - **Image Thumbnail Generation**: Automatic thumbnail generation for both PDF files (using PyMuPDF) and image files (using Pillow), providing consistent preview cards across all media types in the dashboard.
    - **Collections Management**: End-to-end management of collections with linking specifications, search, filtering, cover image upload, and editing functionality.
    - **Collection Cover Images**: Upload and display custom cover images for collections (stored in static/covers/).
    - **Suppliers Management**: Complete CRUD interface for managing suppliers with name, location, contact info, materials (with color-coded tags), custom avatar colors, and automatic counting of associated specifications.
    - **User Management** (Admin only): Complete user administration with view details, edit user info (username, email, role, password), and delete functionality. Includes validation for unique usernames/emails and secure password handling.
    - **User Settings & Profile Management**: Comprehensive user profile and security settings.
    - **Technical Drawings Gallery**: Dedicated page to view all generated drawings with filters, search, pagination, and lightbox functionality.
    - **Workflow Management**: Product status tracking (Draft, In Development, Approved, In Production) and supplier management with dropdown integration in specification forms.
    - **Advanced Filtering**: Multi-criteria filtering and full-text search capabilities across collections, suppliers, specifications, and price ranges.

# External Dependencies

- **OpenAI API**:
    - **GPT-4-Turbo**: Text analysis and structured data extraction from PDFs.
    - **GPT-4o Vision**: Analyzing garment images from PDFs to describe construction details.
    - **GPT-Image-1**: Generating professional technical drawings (flat sketches).
- **Replit Object Storage**: For persistent storage of technical drawings.
- **SQL Database**: Configured via `SQLALCHEMY_DATABASE_URI`.
- **Environment Variables**: `SESSION_SECRET` for session security, `OPENAI_API_KEY` for AI processing.