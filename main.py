import telebot
import requests
import json
import time
import concurrent.futures
import sys
import logging
import re
import traceback
import io
from io import StringIO
from dotenv import load_dotenv
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

logger.info("=== BOT STARTING ===")


load_dotenv()  # загружает переменные из .env файла
BOT_TOKEN = os.getenv("BOT_TOKEN")  # получает значение BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)


SUPER_ADMIN_ID = 7752934373  # Замените на ID супер-админа
SUPER_ADMIN_TAG = "@maxtechops"  # Замените на тег супер-админа

# Вайт-лист пользователей, которым разрешен доступ к боту
# Формат: {user_id: role}
WHITELIST = {
    SUPER_ADMIN_ID: "super-admin",  # Add super admin to whitelist automatically
    7772536909: "admin",  # Пример: замените на реальные ID пользователей
    7310137200: "admin",   # Администратор 1
    6972085618: "admin",   # Администратор 2
    7772536909: "admin",   # Администратор 3
    7600649312: "admin",   # Администратор 4
    7772536804: "user",    # Обычный пользователь 1

}

EXAMPLE_CONFIG = """example@mail.com
API_KEY_EXAMPLE
example.com
anotherdomain.com
192.168.1.1
192.168.1.2
true
true
1"""

def check_access(user_id):
    logger.info(f"Checking access for user ID: {user_id}")
    has_access = user_id in WHITELIST
    logger.info(f"Access for user {user_id}: {'Granted' if has_access else 'Denied'}")
    return has_access


def add_to_whitelist(user_id, new_user_id, role="user"):
    if user_id in WHITELIST and WHITELIST[user_id] in ["admin", "super-admin"]:
        WHITELIST[new_user_id] = role
        return True
    return False


def remove_from_whitelist(user_id, target_user_id):
    if user_id in WHITELIST and WHITELIST[user_id] in ["admin", "super-admin"]:
        if target_user_id in WHITELIST:
            del WHITELIST[target_user_id]
            return True
    return False

def parse_input_text(text):

    logger.info(f"Received text for parsing: {text[:50]}...")
    
    if '|' in text:
        result = parse_cloudflare_format(text)
    else:
        result = parse_regular_format(text)
    
    logger.info(f"Identified accounts: {len(result)}")
    return result

def parse_cloudflare_format(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    accounts = []
    
    i = 0
    while i < len(lines):
        current_line = lines[i]
        i += 1
        
        if '|' in current_line:
            parts = current_line.split('|')
            if len(parts) >= 3: 
                login = parts[0].strip()
                api_key = parts[2].strip() 
                
                domains = []
                while i < len(lines) and not (lines[i].count('.') == 3 and all(part.isdigit() for part in lines[i].split('.'))):
                    domains.append(lines[i])
                    i += 1
                
                if i >= len(lines):
                    break
                    
                ip_api_cdn = lines[i]
                i += 1
                
                if i >= len(lines):
                    break
                    
                ip_www = lines[i]
                i += 1
                
                opportunistic_encryption = False
                tls_1_3 = False
                dns_config_type = 1
                
                if i < len(lines):
                    opportunistic_encryption = lines[i].lower() == 'true'
                    i += 1
                    
                if i < len(lines):
                    tls_1_3 = lines[i].lower() == 'true'
                    i += 1
                    
                if i < len(lines):
                    try:
                        dns_config_type = int(lines[i])
                    except ValueError:
                        dns_config_type = 1
                    i += 1
                
                accounts.append({
                    "login": login,
                    "api_key": api_key,
                    "domains": domains,
                    "ip_api_cdn": ip_api_cdn,
                    "ip_www": ip_www,
                    "opportunistic_encryption": opportunistic_encryption,
                    "tls_1_3": tls_1_3,
                    "dns_config_type": dns_config_type
                })
    
    return accounts

def parse_regular_format(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    accounts = []
    i = 0
    
    while i < len(lines):
        login = lines[i]
        i += 1
        
        if i >= len(lines):
            break
            
        api_key = lines[i]
        i += 1
        
        domains = []
        while i < len(lines) and not (lines[i].count('.') == 3 and all(part.isdigit() for part in lines[i].split('.'))):
            domains.append(lines[i])
            i += 1
            
        if i >= len(lines):
            break
            
        ip_api_cdn = lines[i]
        i += 1
        
        if i >= len(lines):
            break
            
        ip_www = lines[i]
        i += 1
        
        opportunistic_encryption = False
        tls_1_3 = False
        dns_config_type = 1
        
        if i < len(lines):
            opportunistic_encryption = lines[i].lower() == 'true'
            i += 1
            
        if i < len(lines):
            tls_1_3 = lines[i].lower() == 'true'
            i += 1
            
        if i < len(lines):
            try:
                dns_config_type = int(lines[i])
            except ValueError:
                dns_config_type = 1
            i += 1
            
        accounts.append({
            "login": login,
            "api_key": api_key,
            "domains": domains,
            "ip_api_cdn": ip_api_cdn,
            "ip_www": ip_www,
            "opportunistic_encryption": opportunistic_encryption,
            "tls_1_3": tls_1_3,
            "dns_config_type": dns_config_type
        })
        
    return accounts

def get_headers(login, api_key):
    return {
        "X-Auth-Email": login,
        "X-Auth-Key": api_key,
        "Content-Type": "application/json"
    }

def create_zone(login, api_key, domain):
    url = "https://api.cloudflare.com/client/v4/zones"
    data = {"name": domain, "jump_start": True}
    try:
        response = requests.post(url, headers=get_headers(login, api_key), json=data)
        return response.json()
    except Exception as e:
        logger.error(f"Error creating zone {domain}: {str(e)}")
        return {"success": False, "error": str(e)}

def check_zone_exists(login, api_key, domain):
    url = "https://api.cloudflare.com/client/v4/zones"
    params = {"name": domain}
    try:
        response = requests.get(url, headers=get_headers(login, api_key), params=params)
        data = response.json()
        if data.get('success') and data.get('result') and len(data['result']) > 0:
            return data['result'][0]['id']
        return None
    except Exception as e:
        logger.error(f"Error checking if zone exists {domain}: {str(e)}")
        return None

def delete_zone(login, api_key, zone_id):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}"
    try:
        response = requests.delete(url, headers=get_headers(login, api_key))
        return response.json()
    except Exception as e:
        logger.error(f"Error deleting zone {zone_id}: {str(e)}")
        return {"success": False, "error": str(e)}

def get_nameservers(login, api_key, zone_id):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}"
    try:
        response = requests.get(url, headers=get_headers(login, api_key))
        data = response.json()
        return data['result']['name_servers'] if 'result' in data and 'name_servers' in data['result'] else None
    except Exception as e:
        logger.error(f"Error getting nameservers for zone {zone_id}: {str(e)}")
        return None

def delete_existing_records(login, api_key, zone_id):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    try:
        response = requests.get(url, headers=get_headers(login, api_key))
        records = response.json().get("result", [])
        
        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(
                    requests.delete, 
                    f"{url}/{record['id']}", 
                    headers=get_headers(login, api_key)
                ) 
                for record in records
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    errors.append(str(e))
        
        return len(errors) == 0
    except Exception as e:
        logger.error(f"Error deleting DNS records for zone {zone_id}: {str(e)}")
        return False

def create_dns_record(login, api_key, zone_id, type, name, content, proxied=True):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    data = {
        "type": type,
        "name": name,
        "content": content,
        "ttl": 1,
        "proxied": proxied
    }
    try:
        response = requests.post(url, headers=get_headers(login, api_key), json=data)
        return response.json()
    except Exception as e:
        logger.error(f"Error creating DNS record {type} {name} -> {content}: {str(e)}")
        return {"success": False, "error": str(e)}

def configure_ssl(login, api_key, zone_id, opportunistic_encryption, tls_1_3):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/settings"
    settings = {
        "opportunistic_encryption": "on" if opportunistic_encryption else "off",
        "tls_1_3": "on" if tls_1_3 else "off",
        "min_tls_version": "1.2",
        "always_use_https": "on"
    }
    
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(
                requests.patch, 
                f"{url}/{setting}", 
                headers=get_headers(login, api_key), 
                json={"value": value}
            ) 
            for setting, value in settings.items()
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                response = future.result()
                if not response.json().get('success', False):
                    errors.append(response.json().get('errors', ['Unknown error'])[0])
            except Exception as e:
                errors.append(str(e))
    
    return len(errors) == 0

def setup_dns_config_type_1(login, api_key, zone_id, domain, ip_api_cdn, ip_www, log=None):
    """Configuration type 1 for DNS setup"""
    records = [
        {"type": "A", "name": "api", "content": ip_api_cdn, "proxied": True},
        {"type": "A", "name": "cdn", "content": ip_api_cdn, "proxied": True},
        {"type": "A", "name": "@", "content": ip_www, "proxied": True},
        {"type": "A", "name": "www", "content": ip_www, "proxied": True}
    ]
    
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for record in records:
            record_name = record["name"] if record["name"] != "@" else domain
            futures.append(
                executor.submit(
                    create_dns_record,
                    login, api_key, zone_id, 
                    record["type"], record_name, record["content"], record["proxied"]
                )
            )
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if not result.get('success'):
                    error_msg = f"Failed to add DNS record: {result.get('errors', ['Unknown error'])[0]}"
                    errors.append(error_msg)
                    if log:
                        log.append(error_msg)
                    continue
                
                record_name = result.get('result', {}).get('name', 'unknown')
                record_content = result.get('result', {}).get('content', 'unknown')
                success_msg = f"DNS record {record_name} -> {record_content} added (Proxied)"
                if log:
                    log.append(success_msg)
            except Exception as e:
                errors.append(str(e))
                if log:
                    log.append(f"Error: {str(e)}")
    
    return len(errors) == 0

def setup_dns_config_type_2(login, api_key, zone_id, domain, ip_www, log=None):
    """Configuration type 2 for DNS setup"""
    records = [
        {"type": "CNAME", "name": "partners", "content": domain, "proxied": True},
        {"type": "A", "name": "*", "content": ip_www, "proxied": True},
        {"type": "A", "name": "@", "content": ip_www, "proxied": True},
        {"type": "A", "name": "www", "content": ip_www, "proxied": True}
    ]
    
    # Create records in parallel
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for record in records:
            record_name = record["name"] if record["name"] != "@" else domain
            futures.append(
                executor.submit(
                    create_dns_record,
                    login, api_key, zone_id, 
                    record["type"], record_name, record["content"], record["proxied"]
                )
            )
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if not result.get('success'):
                    error_msg = f"Failed to add DNS record: {result.get('errors', ['Unknown error'])[0]}"
                    errors.append(error_msg)
                    if log:
                        log.append(error_msg)
                    continue
                
                record_name = result.get('result', {}).get('name', 'unknown')
                record_content = result.get('result', {}).get('content', 'unknown')
                success_msg = f"DNS record {record_name} -> {record_content} added (Proxied)"
                if log:
                    log.append(success_msg)
            except Exception as e:
                errors.append(str(e))
                if log:
                    log.append(f"Error: {str(e)}")
    
    return len(errors) == 0

def update_progress_message(chat_id, message_id, progress, total, login, stage="Processing domains"):
    progress_percentage = min(100, int(progress / total * 100))
    progress_bar = '▓' * (progress_percentage // 10) + '░' * (10 - progress_percentage // 10)
    
    text = (
        f"⚙️ Working with account: {login}\n"
        f"👨‍💻 {stage}:\n"
        f"[{progress_bar}] {progress_percentage}%\n"
        f"🔄 Processed {progress}/{total} domains"
    )
    
    try:
        bot.edit_message_text(text, chat_id, message_id, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error updating progress message: {str(e)}")

def setup_zones(account, chat_id, all_accounts_info):
    login = account["login"]
    api_key = account["api_key"]
    domains = account["domains"]
    ip_api_cdn = account["ip_api_cdn"]
    ip_www = account["ip_www"]
    dns_config_type = account["dns_config_type"]
    
    ssl_settings = {
        "opportunistic_encryption": account["opportunistic_encryption"],
        "tls_1_3": account["tls_1_3"]
    }
    
    zone_info = {}
    errors = []
    log_messages = []
    

    progress_message = bot.send_message(
        chat_id, 
        f"⚙️ Working with account: {login}\n👨‍💻 Preparation:\n[░░░░░░░░░░] 0%\n🔄 Processed 0/{len(domains)} domains"
    )
    message_id = progress_message.message_id
    

    for index, domain in enumerate(domains):
        logger.info(f"Processing domain {domain} for account {login}")
        update_progress_message(chat_id, message_id, index, len(domains), login, "Checking domain")
        
        try:

            existing_zone_id = check_zone_exists(login, api_key, domain)
            if existing_zone_id:
                zone_info[domain] = existing_zone_id
            else:

                zone_response = create_zone(login, api_key, domain)
                if zone_response.get('success'):
                    zone_id = zone_response['result']['id']
                    zone_info[domain] = zone_id
                else:
                    error_msg = zone_response.get('errors', [{'message': 'Unknown error'}])[0].get('message')
                    fail_msg = f"❌ Failed to add domain {domain}: {error_msg}"
                    errors.append(fail_msg)
                    log_messages.append(fail_msg)
                    continue

            update_progress_message(chat_id, message_id, index + 0.33, len(domains), login, "Setting up DNS")
            
            if not delete_existing_records(login, api_key, zone_info[domain]):
                error_msg = f"❌ Error deleting existing DNS records for {domain}"
                errors.append(error_msg)
                log_messages.append(error_msg)


            dns_success = False
            if dns_config_type == 1:
                dns_success = setup_dns_config_type_1(login, api_key, zone_info[domain], domain, ip_api_cdn, ip_www, log_messages)
            elif dns_config_type == 2:
                dns_success = setup_dns_config_type_2(login, api_key, zone_info[domain], domain, ip_www, log_messages)
                
            if not dns_success:
                error_msg = f"❌ Error configuring DNS records for {domain}"
                errors.append(error_msg)
                log_messages.append(error_msg)
            
            update_progress_message(chat_id, message_id, index + 0.66, len(domains), login, "Configuring SSL")
            
            if not configure_ssl(login, api_key, zone_info[domain], ssl_settings["opportunistic_encryption"], ssl_settings["tls_1_3"]):
                error_msg = f"❌ Error configuring SSL for {domain}"
                errors.append(error_msg)
                log_messages.append(error_msg)
                
        except Exception as e:
            error_msg = f"❌ Error processing domain {domain}: {str(e)}"
            errors.append(error_msg)
            log_messages.append(error_msg)
    
    update_progress_message(chat_id, message_id, len(domains), len(domains), login, "Getting NS data")
    

    ns_servers = []
    for domain, zone_id in zone_info.items():
        servers = get_nameservers(login, api_key, zone_id)
        if servers:
            ns_servers = servers
            break 
    

    account_info = {
        "login": login,
        "ns_servers": ns_servers,
        "errors": errors,
        "domains": list(zone_info.keys())  
    }
    all_accounts_info.append(account_info)
    

    try:
        bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}")
    
    return account_info

def send_final_summary(chat_id, all_accounts_info):

    has_errors = any(len(acc["errors"]) > 0 for acc in all_accounts_info)
    
    if has_errors:
        status_message = "⚠️ Программа завершила работу с ошибками\n\n"
    else:
        status_message = "✅ Программа завершила работу без ошибок\n\n"
    

    for account_info in all_accounts_info:
        login = account_info["login"]
        ns_servers = account_info["ns_servers"]

        status_message += f"🟠 {login}\n\n"

        if "domains" in account_info and account_info["domains"]:
            status_message += "🌐 Настроенные домены:\n"
            for domain in account_info["domains"]:
                status_message += f"- {domain}\n"
            status_message += "\n"
        

        if ns_servers:
            status_message += "🔧 NS серверы:\n"
            for ns in ns_servers:
                status_message += f"<code>{ns}</code>\n"
        else:
            status_message += "❌ Не удалось получить NS серверы\n"
        
        status_message += "\n"
    

    try:
        bot.send_message(chat_id, status_message, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error sending final summary: {str(e)}")

        simplified_message = status_message.replace("<code>", "").replace("</code>", "")
        bot.send_message(chat_id, simplified_message)


@bot.message_handler(commands=['start'])
def welcome_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    logger.info(f"User {user_id} started the bot")

    if check_access(user_id):
        welcome_text = (
            "👋 Добро пожаловать в Cloudflare Setup Bot!\n\n"
            "Этот бот помогает настраивать множество доменов в Cloudflare.\n\n"
            "📋 Доступные команды:\n"
            "/format - Показать примеры поддерживаемых форматов данных\n"
        )
        

        if user_id in WHITELIST and WHITELIST[user_id] in ["admin", "super-admin"]:
            welcome_text += (
            "\n📊 Команды администратора:\n"
            "/add_user - Добавить нового пользователя в белый список\n"
            "/remove_user - Удалить пользователя из белого списка\n"
            "/users - Список всех пользователей в белом списке\n"
           )
            welcome_text += (
            "\nДля настройки доменов просто вставьте свои данные конфигурации в одном из поддерживаемых форматов.\n"
            "Используйте /format, чтобы увидеть примеры форматов конфигурации."
            )
        
        try:
            bot.send_message(chat_id, welcome_text)
        except Exception as e:
            logger.error(f"Error sending welcome message: {str(e)}")
    else:
        logger.warning(f"Access denied to user {user_id}")
        try:
            bot.send_message(chat_id, f"You don't have access to this bot. Contact admin {SUPER_ADMIN_TAG} to request access.")
        except Exception as e:
            logger.error(f"Error sending access denied message: {str(e)}")


@bot.message_handler(commands=['add_user'])
def add_user_command(message):
    user_id = message.from_user.id

    if user_id in WHITELIST and WHITELIST[user_id] in ["admin", "super-admin"]:
        try:

            command_parts = message.text.split()
            if len(command_parts) >= 2:
                new_user_id = int(command_parts[1])
                role = command_parts[2] if len(command_parts) >= 3 else "user"
                
                WHITELIST[new_user_id] = role
                bot.reply_to(message, f"✅ User {new_user_id} added to whitelist with role {role}")
                logger.info(f"User {user_id} added {new_user_id} to whitelist with role {role}")
            else:
                bot.reply_to(message, "❌ Invalid command format. Use: /add_user ID role")
        except ValueError:
            bot.reply_to(message, "❌ User ID must be a number")
        except Exception as e:
            bot.reply_to(message, f"❌ Error adding user: {str(e)}")
    else:

        access_denied_message = f"❌ You don't have permissions to add users to whitelist. Contact {SUPER_ADMIN_TAG}"
        bot.reply_to(message, access_denied_message)


@bot.message_handler(commands=['remove_user'])
def remove_user_command(message):
    user_id = message.from_user.id
    

    if user_id in WHITELIST and WHITELIST[user_id] in ["admin", "super-admin"]:
        try:

            command_parts = message.text.split()
            if len(command_parts) >= 2:
                target_user_id = int(command_parts[1])
                
                if target_user_id in WHITELIST:
                    del WHITELIST[target_user_id]
                    bot.reply_to(message, f"✅ User {target_user_id} removed from whitelist")
                    logger.info(f"User {user_id} removed {target_user_id} from whitelist")
                else:
                    bot.reply_to(message, f"❌ User {target_user_id} not found in whitelist")
            else:
                bot.reply_to(message, "❌ Invalid command format. Use: /remove_user ID")
        except ValueError:
            bot.reply_to(message, "❌ User ID must be a number")
        except Exception as e:
            bot.reply_to(message, f"❌ Error removing user: {str(e)}")
    else:

        access_denied_message = f"❌ You don't have permissions to remove users from whitelist. Contact {SUPER_ADMIN_TAG}"
        bot.reply_to(message, access_denied_message)


@bot.message_handler(commands=['users'])
def list_users_command(message):
    user_id = message.from_user.id
    
    if user_id in WHITELIST and WHITELIST[user_id] in ["admin", "super-admin"]:
        try:
            if WHITELIST:
                users_list = "👥 Users in whitelist:\n\n"
                for uid, role in WHITELIST.items():
                    users_list += f"ID: {uid}, Role: {role}\n"
                bot.reply_to(message, users_list)
            else:
                bot.reply_to(message, "👥 Whitelist is empty")
        except Exception as e:
            bot.reply_to(message, f"❌ Error getting user list: {str(e)}")
            logger.error(f"Error in list_users command: {str(e)}")
    else:
        access_denied_message = f"❌ You don't have permissions to view user list. Contact {SUPER_ADMIN_TAG}"
        bot.reply_to(message, access_denied_message)

@bot.message_handler(commands=['format'])
def show_formats(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    logger.info(f"User {user_id} requested format examples")
    
    if check_access(user_id):
        format_text = (
            "📋 Примеры форматов данных:\n\n"
            "1️⃣ Стандартный формат:\n"
            "example@mail.com\n"
            "API_KEY_EXAMPLE\n"
            "example.com\n"
            "anotherdomain.com\n"
            "192.168.1.1\n"
            "192.168.1.2\n"
            "true\n"
            "true\n"
            "1\n\n"
            "2️⃣ Формат из Cloudflare:\n"
            "example@mail.com | X | API_KEY_EXAMPLE\n"
            "domain1.com\n"
            "domain2.com\n"
            "192.168.1.1\n"
            "192.168.1.2\n"
            "true\n"
            "true\n"
            "1"
        )
        
        explanation_text = (
            "ℹ️ Пояснение параметров:\n\n"
            "1. Email аккаунта Cloudflare\n"
            "2. API ключ\n" 
            "3. Список доменов (каждый с новой строки)\n"
            "4. IP-адрес для API и CDN\n"
            "5. IP-адрес для WWW\n"
            "6. Opportunistic Encryption (true/false)\n"
            "7. TLS 1.3 (true/false)\n"
            "8. Тип DNS конфигурации (1 или 2)"
        )
        
        try:
            bot.send_message(chat_id, format_text)
            bot.send_message(chat_id, explanation_text)
        except Exception as e:
            logger.error(f"Error sending format examples: {str(e)}")
    else:
        logger.warning(f"Access denied to user {user_id}")
        try:
            bot.send_message(chat_id, f"You don't have access to this bot. Contact admin {SUPER_ADMIN_TAG}.")
        except Exception as e:
            logger.error(f"Error sending access denied message: {str(e)}")

@bot.message_handler(func=lambda message: not message.text.startswith('/'), content_types=['text'])
def process_text(message):
    user_id = message.from_user.id

    logger.info(f"Text message received from user {user_id}: {message.text[:20]}...")
    
    if not check_access(user_id):
        logger.warning(f"User {user_id} tried to send data without access")
        bot.reply_to(message, f"You don't have access to this bot. Contact admin {SUPER_ADMIN_TAG}.")
        return
    
    text = message.text.strip()
    if text.startswith('/'):
        logger.info(f"Skipping message that looks like a command: {text[:20]}...")
        return
    
    logger.info(f"Processing data from user {user_id}")
    
    try:
        accounts = parse_input_text(text)
        
        if not accounts:
            bot.reply_to(message, "❌ Could not recognize data format. Check your input.")
            return
        
        
        all_accounts_info = []
        
        for account in accounts:
            setup_zones(account, message.chat.id, all_accounts_info)
        

        send_final_summary(message.chat.id, all_accounts_info)
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        logger.error(traceback.format_exc())
        bot.reply_to(message, f"❌ Error processing data: {str(e)}")

if __name__ == "__main__":
    logger.info("=== BOT STARTING ===")
    logger.info(f"Current whitelist: {WHITELIST}")
    
    try:
        while True:
            try:
                logger.info("Starting bot in polling mode...")
                bot.polling(none_stop=True, interval=1, timeout=60)
            except Exception as e:
                logger.error(f"Error in polling loop: {str(e)}")
                logger.error(traceback.format_exc())
                time.sleep(10)  # Pause before restarting
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error: {str(e)}")
        logger.critical(traceback.format_exc())
    finally:
        logger.info("=== BOT SHUTDOWN ===")