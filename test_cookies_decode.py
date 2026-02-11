import base64
import re

# Вставьте сюда значение из Railway переменной YOUTUBE_COOKIES_BASE64
cookies_env = """
ВСТАВЬТЕ_СЮДА_ЗНАЧЕНИЕ_ИЗ_RAILWAY
"""

# Применяем ту же логику очистки, что и в боте
cookies_env = re.sub(r'[^A-Za-z0-9+/=]', '', cookies_env).strip()

# Ищем начало Netscape файла
if 'IyB' in cookies_env:
    print(f"✅ Найден маркер 'IyB' на позиции: {cookies_env.find('IyB')}")
    cookies_env = cookies_env[cookies_env.find('IyB'):]
else:
    print("❌ Маркер 'IyB' НЕ найден! Это означает, что строка не содержит Netscape cookies.")

# Убираем ведущие '='
cookies_env = cookies_env.lstrip('=')

# Добавляем padding
missing_padding = len(cookies_env) % 4
if missing_padding:
    cookies_env += '=' * (4 - missing_padding)

print(f"\n📏 Длина очищенной строки: {len(cookies_env)}")
print(f"🔤 Первые 50 символов: {cookies_env[:50]}")

# Декодируем
try:
    cookies_bytes = base64.b64decode(cookies_env)
    try:
        cookies_content = cookies_bytes.decode('utf-8')
    except UnicodeDecodeError:
        print("⚠️ UTF-8 не сработал, используем latin-1...")
        cookies_content = cookies_bytes.decode('latin-1')
    
    print(f"\n📊 Декодированный контент (первые 100 символов):")
    print(cookies_content[:100])
    
    if cookies_content.startswith('# Netscape'):
        print("\n✅ Формат Netscape КОРРЕКТНЫЙ!")
    else:
        print("\n❌ Формат НЕ Netscape!")
        print(f"Начало файла: {repr(cookies_content[:50])}")
        
except Exception as e:
    print(f"\n❌ Ошибка декодирования: {e}")
