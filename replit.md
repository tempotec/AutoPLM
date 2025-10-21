# Overview

This is a Flask-based technical specification management platform designed for fashion/textile industry workflows. The system allows users to upload PDF files containing technical specifications (fichas técnicas) and uses OpenAI's API to extract structured information through OCR processing. The platform features role-based access with admin controls for user management and comprehensive tracking of all user activities.

## Recent Update (October 21, 2025)

Added advanced AI-powered measurement extraction and technical drawing generation capabilities:
- **Structured Measurements Extraction**: Uses OpenAI Vision (GPT-4o) to extract detailed measurements from PDFs in JSON format, supporting size scales (PP, P, M, G, GG) with tolerances
- **Technical Sketch Detection**: Automatically detects if PDF already contains technical drawings (flat sketches) using AI vision
- **Automated Drawing Generation**: Generates professional technical flat sketches using DALL-E-3 when no croqui exists in the PDF, respecting extracted measurements
- **Manual Regeneration**: Users can manually trigger technical drawing regeneration with a button
- **Image Extraction**: Uses PyMuPDF to extract high-quality images from PDFs for reference and processing

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Frontend Architecture
- **Template Engine**: Jinja2 templates with Bootstrap 5 for responsive UI
- **Styling**: Custom CSS with Font Awesome icons for enhanced user experience
- **Forms**: Flask-WTF for secure form handling with CSRF protection
- **File Upload**: Drag-and-drop interface for PDF uploads with client-side validation

## Backend Architecture
- **Web Framework**: Flask with modular route structure
- **Database ORM**: SQLAlchemy for database abstraction and relationship management
- **Authentication**: Session-based authentication with password hashing using Werkzeug
- **File Processing**: PyPDF2 for PDF text extraction combined with OpenAI API for intelligent data parsing
- **Security**: CSRF protection, secure filename handling, and file size limits

## Data Storage Solutions
- **Primary Database**: SQL database (configured via DATABASE_URL environment variable)
- **File Storage**: Local filesystem storage for uploaded PDF files
- **Session Management**: Flask sessions for user state management

## Authentication and Authorization
- **User Roles**: Two-tier system with regular users and administrators
- **Access Control**: Decorator-based route protection (@admin_required)
- **Password Security**: Werkzeug password hashing for secure credential storage

## External Dependencies
- **OpenAI API**: 
  - GPT-4-Turbo: For general text analysis and structured data extraction
  - GPT-4o: For vision-based measurement extraction from PDF images
  - DALL-E-3: For generating technical flat sketches based on measurements and reference images
- **Database**: PostgreSQL database via SQLALCHEMY_DATABASE_URI
- **PyMuPDF (fitz)**: For advanced PDF processing and image extraction
- **Environment Variables**: SESSION_SECRET for session security, OPENAI_API_KEY for AI processing

## Data Processing Pipeline

The system now implements a comprehensive dual-processing pipeline:

### Primary Pipeline (Original - General Data Extraction)
Processes technical specifications containing product identification, commercial information, delivery schedules, team assignments, materials, and basic technical measurements. The AI integration transforms unstructured PDF content into structured database records.

### Secondary Pipeline (New - Measurements & Drawings)
1. **Image Extraction**: Extracts all images from PDF using PyMuPDF, ranked by quality
2. **Structured Measurement Extraction**: 
   - Uses OpenAI Vision to analyze both text and images
   - Extracts measurements in structured JSON format
   - Supports multiple size scales and base sizes
   - Includes tolerances and observações
   - Stores: measurements_json, size_scale_json, measurement_base_size, tolerances_json
3. **Technical Sketch Detection**: 
   - Analyzes extracted images to detect existing technical drawings
   - Sets has_technical_sketch flag
4. **Conditional Drawing Generation**:
   - If no technical sketch exists and measurements are available
   - Generates front and back view flat sketches using DALL-E-3
   - Respects extracted measurements and proportions
   - Stores paths: generated_front_image, generated_back_image
5. **Manual Regeneration**: Users can trigger regeneration via UI button

## New Database Fields (Specification Model)
- measurements_json: Complete structured measurements JSON
- size_scale_json: Array of available sizes
- measurement_base_size: Base/pilot size
- tolerances_json: Tolerances per measurement type
- measurements_status: Processing status for measurements
- reference_image_path: Best reference image from PDF
- has_technical_sketch: Boolean indicating if PDF has croqui
- generated_front_image: Path to AI-generated front view
- generated_back_image: Path to AI-generated back view
- sketch_generation_status: Status of drawing generation