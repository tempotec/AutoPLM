# Overview

This Flask-based platform manages technical specifications for the fashion/textile industry. It processes PDF files and image files (JPG, PNG, JPEG) containing technical specs using OpenAI's API for OCR and structured data extraction. A key feature is AI-powered technical drawing generation using GPT-Image-1, which automatically creates professional flat sketches with precise dimensions and measurement points (POMs) based on extracted specifications and visual analysis of garment images. The system includes role-based access control for users and administrators, alongside comprehensive activity tracking.

## Recent Changes (October 27, 2025)
- **Image Upload Support**: Extended upload functionality to accept image files (JPG, PNG, JPEG) in addition to PDFs.
- **Dual Processing Pipeline**: Implemented intelligent file type detection with separate processing paths for images and PDFs.
- **Enhanced Visual Analysis**: Images are directly analyzed with GPT-4o Vision for structured data extraction.
- **Robust Fallback**: When Vision returns text instead of JSON, the system processes it through OpenAI extraction pipeline to ensure fields are always populated.
- **UI Updates**: Upload interface now accepts multiple formats with appropriate file type icons and validation.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## UI/UX Decisions
- **Frontend**: Jinja2 templates, Bootstrap 5 for responsive design.
- **Styling**: Custom CSS, Font Awesome icons.
- **Forms**: Flask-WTF for secure handling, CSRF protection.
- **File Upload**: Drag-and-drop interface with client-side validation.

## Technical Implementations
- **Web Framework**: Flask with a modular route structure.
- **Database ORM**: SQLAlchemy for database abstraction.
- **Authentication**: Session-based, with Werkzeug for password hashing.
- **File Processing**: PyPDF2 for PDF text and image extraction.
- **AI Processing**: OpenAI API for data parsing, vision analysis, and image generation.
- **Security**: CSRF protection, secure filename handling, file size limits.

## System Design Choices
- **Data Storage**: SQL database for primary data, local filesystem for uploaded PDFs and generated drawings.
- **Session Management**: Flask sessions for user state.
- **Authentication & Authorization**: Two-tier user roles (regular, admin) with decorator-based access control.
- **AI Integration Workflow**:
    1. PDF upload and data extraction (GPT-4-Turbo).
    2. Image extraction from PDF (PyPDF2).
    3. Visual analysis of garment images (GPT-4o Vision) to produce structured JSON.
    4. Technical drawing prompt construction using extracted data and visual analysis.
    5. Professional flat sketch generation with dimensions (GPT-Image-1).
    6. Local storage of generated drawings and database record of filenames.

## Feature Specifications
- **Data Extraction**: Transforms unstructured PDF content into structured records (product identification, commercial info, deadlines, materials, technical measurements).
- **Technical Drawing Generation**: Produces production-ready, dimensioned flat sketches (flat dimensionado) with:
    - Front and back views, aligned vertically, to scale.
    - Numbered Measurement Points (POMs) with tolerances.
    - Professional dimensioning (cotagem) with specific line weights, arrow styles, and text positioning.
    - Technical representation of textures, constructions, and details.
    - Local storage of generated drawings (base64 decoded).
    - Image Normalization: Corrects perspective, aligns central axis, ensures symmetry.
- **Output**: Generates a single, dimensioned image per request; a clean (non-dimensioned) version would require a separate generation workflow.
- **Key Innovations**: Utilizes actual images from PDFs for AI analysis, integrates POMs from specification data, adheres to professional cotagem standards, and uses local storage for generated assets.

# External Dependencies

- **OpenAI API**:
    - **GPT-4-Turbo**: Text analysis and structured data extraction from PDFs.
    - **GPT-4o Vision**: Analyzing garment images from PDFs to describe construction details in structured JSON.
    - **GPT-Image-1**: Generating professional technical drawings (flat sketches) based on specifications and visual analysis.
- **SQL Database**: Configured via `SQLALCHEMY_DATABASE_URI`.
- **Environment Variables**: `SESSION_SECRET` for session security, `OPENAI_API_KEY` for AI processing.