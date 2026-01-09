from app.utils.auth import login_required, admin_required
from app.utils.files import (
    is_image_file,
    is_pdf_file,
    convert_image_to_base64,
    convert_image_to_data_url,
    get_image_mimetype,
)
from app.utils.logging import log_activity, rpa_info, rpa_warn, rpa_error, init_rpa_monitor
from app.utils.pdf import (
    extract_text_from_pdf, 
    extract_images_from_pdf, 
    generate_pdf_thumbnail,
    generate_image_thumbnail
)
from app.utils.ai import (
    analyze_images_with_gpt4_vision,
    process_specification_with_openai,
    build_technical_drawing_prompt,
    has_technical_measurements
)
from app.utils.helpers import convert_value_to_string, get_or_create_supplier

__all__ = [
    'login_required',
    'admin_required',
    'is_image_file',
    'is_pdf_file',
    'convert_image_to_base64',
    'convert_image_to_data_url',
    'get_image_mimetype',
    'log_activity',
    'rpa_info',
    'rpa_warn',
    'rpa_error',
    'init_rpa_monitor',
    'extract_text_from_pdf',
    'extract_images_from_pdf',
    'generate_pdf_thumbnail',
    'generate_image_thumbnail',
    'analyze_images_with_gpt4_vision',
    'process_specification_with_openai',
    'build_technical_drawing_prompt',
    'has_technical_measurements',
    'convert_value_to_string',
    'get_or_create_supplier'
]
