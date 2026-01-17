"""
文件处理模块 - 用于调研记录的文件上传和文本提取
"""
import io
import os


def extract_text_from_file(file_content: bytes, file_type: str) -> str:
    """
    从上传的文件中提取文本内容

    Args:
        file_content: 文件二进制内容
        file_type: 文件类型（pdf, docx, doc, txt, md, rtf）

    Returns:
        提取的文本内容
    """
    try:
        if file_type in ('txt', 'md'):
            # TXT/MD 文件直接解码
            try:
                return file_content.decode('utf-8')
            except UnicodeDecodeError:
                return file_content.decode('gbk', errors='ignore')

        elif file_type == 'rtf':
            # RTF 文件处理
            try:
                from striprtf.striprtf import rtf_to_text
                try:
                    text = file_content.decode('utf-8')
                except UnicodeDecodeError:
                    text = file_content.decode('gbk', errors='ignore')
                return rtf_to_text(text)
            except ImportError:
                # striprtf 未安装，尝试简单提取
                try:
                    text = file_content.decode('utf-8', errors='ignore')
                except:
                    text = file_content.decode('gbk', errors='ignore')
                # 简单去除 RTF 控制符
                import re
                text = re.sub(r'\\[a-z]+\d*\s?', '', text)
                text = re.sub(r'[{}]', '', text)
                return text.strip()
            except Exception as e:
                print(f"RTF 解析失败: {e}")
                return f"[RTF 解析失败: {e}]"

        elif file_type == 'pdf':
            # PDF 文件使用 PyPDF2
            try:
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                text_parts = []
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                return '\n'.join(text_parts)
            except ImportError:
                print("PyPDF2 未安装，无法解析 PDF")
                return "[PDF 文件，需要安装 PyPDF2 才能提取文本]"
            except Exception as e:
                print(f"PDF 解析失败: {e}")
                return f"[PDF 解析失败: {e}]"

        elif file_type in ('docx', 'doc'):
            # Word 文件使用 python-docx
            try:
                from docx import Document
                doc = Document(io.BytesIO(file_content))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                return '\n'.join(paragraphs)
            except ImportError:
                print("python-docx 未安装，无法解析 Word 文档")
                return "[Word 文件，需要安装 python-docx 才能提取文本]"
            except Exception as e:
                print(f"Word 解析失败: {e}")
                return f"[Word 解析失败: {e}]"

        return ''

    except Exception as e:
        print(f"文件文本提取失败: {e}")
        return ''


def upload_to_supabase_storage(file_content: bytes, file_name: str, content_type: str, folder: str = 'research') -> str:
    """
    上传文件到 Supabase Storage

    Args:
        file_content: 文件二进制内容
        file_name: 原始文件名
        content_type: MIME 类型
        folder: 存储目录

    Returns:
        文件的公共访问 URL
    """
    try:
        from modules.supabase_client import get_admin
        import uuid

        supabase = get_admin()

        # 生成唯一文件名
        file_ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
        storage_path = f"{folder}/{uuid.uuid4()}.{file_ext}"

        # 上传到 storage
        supabase.storage.from_('research-files').upload(
            storage_path,
            file_content,
            {'content-type': content_type}
        )

        # 获取公共 URL
        public_url = supabase.storage.from_('research-files').get_public_url(storage_path)
        return public_url

    except Exception as e:
        print(f"上传文件到 Supabase Storage 失败: {e}")
        return None


def get_allowed_extensions():
    """获取允许上传的文件扩展名"""
    return {'pdf', 'docx', 'doc', 'txt', 'md', 'rtf'}


def validate_file_type(filename: str) -> bool:
    """验证文件类型是否允许"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower()
    return ext in get_allowed_extensions()


def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].lower()
