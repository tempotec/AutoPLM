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
- **Image Display**: Dashboard cards display PDF preview thumbnails, technical drawings, or product images with proper styling and fallbacks.
- **Navigation**: Professional sidebar with key sections and user profile display.

## Technical Implementations
- **Web Framework**: Flask with a modular route structure.
- **Database ORM**: SQLAlchemy for database abstraction.
- **Authentication**: Session-based, with Werkzeug for password hashing and role-based access control (admin, stylist).
- **File Processing**: PyPDF2 for PDF text and image extraction; PyMuPDF for PDF thumbnail generation.
- **AI Processing**: OpenAI API for data parsing, vision analysis, and image generation.
- **Data Storage**: SQL database for primary data. Replit Object Storage for technical drawings, with local filesystem fallback.
- **Security**: CSRF protection, secure filename handling, file size limits.

## System Design Choices
- **Data Model**: Includes Specifications, Collections, and relationships between them.
- **AI Integration Workflow**:
    1. PDF/Image upload and data extraction (GPT-4-Turbo).
    2. Image extraction from PDF (PyPDF2).
    3. Visual analysis of garment images (GPT-4o Vision) to produce structured JSON.
    4. Technical drawing prompt construction using extracted data and visual analysis.
    5. Clean flat sketch generation (GPT-Image-1) without measurements.
    6. Object Storage for generated drawings and database record of URLs.
- **Feature Set**:
    - **Data Extraction**: Transforms unstructured PDF content into structured records (product identification, commercial info, deadlines, materials, technical measurements).
    - **Technical Drawing Generation**: Produces professional flat sketches focused on visual representation without dimensions.
    - **Collections Management**: End-to-end management of collections with linking specifications, search, and filtering.
    - **User Settings & Profile Management**: Comprehensive user profile and security settings.
    - **Technical Drawings Gallery**: Dedicated page to view all generated drawings with filters, search, pagination, and lightbox functionality.
    - **Workflow Management**: Product status tracking (Draft, In Development, Approved, In Production) and supplier management.
    - **Advanced Filtering**: Multi-criteria filtering and full-text search capabilities.

# External Dependencies

- **OpenAI API**:
    - **GPT-4-Turbo**: Text analysis and structured data extraction from PDFs.
    - **GPT-4o Vision**: Analyzing garment images from PDFs to describe construction details.
    - **GPT-Image-1**: Generating professional technical drawings (flat sketches).
- **Replit Object Storage**: For persistent storage of technical drawings.
- **SQL Database**: Configured via `SQLALCHEMY_DATABASE_URI`.
- **Environment Variables**: `SESSION_SECRET` for session security, `OPENAI_API_KEY` for AI processing.