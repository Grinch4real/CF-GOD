import telebot
import requests
import random
import string
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
import queue
import threading
import time

task_queue = queue.Queue()
task_lock = threading.Lock()
current_processing = False

waiting_users = {}

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


load_dotenv()  
BOT_TOKEN = os.getenv("BOT_TOKEN") 

bot = telebot.TeleBot(BOT_TOKEN)


SUPER_ADMIN_ID = os.getenv("SUPER_ADMIN_ID")  
SUPER_ADMIN_TAG = os.getenv("SUPER_ADMIN_TAG")  

WHITELIST = {int(item.split(':')[0]): item.split(':')[1] for item in os.getenv('WHITELIST', '').split(',')}

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

def setup_dns_config_type_3(login, api_key, zone_id, domain, ip_api_cdn, ip_www, log=None):
    """Configuration type 3 for DNS setup - includes type 1 settings plus additional Google Workspace related records"""

    
    # First set up the basic records from type 1
    basic_records_success = setup_dns_config_type_1(login, api_key, zone_id, domain, ip_api_cdn, ip_www, log)
    
    if not basic_records_success:
        if log:
            log.append("❌ Failed to set up base records, cannot continue with additional records")
        return False
    
    # Additional records for type 3
    additional_records = [
        # MX Records
        {"type": "MX", "name": "@", "content": "ASPMX.L.GOOGLE.COM", "priority": 1, "proxied": False},
        {"type": "MX", "name": "@", "content": "ALT1.ASPMX.L.GOOGLE.COM", "priority": 5, "proxied": False},
        {"type": "MX", "name": "@", "content": "ALT2.ASPMX.L.GOOGLE.COM", "priority": 5, "proxied": False},
        {"type": "MX", "name": "@", "content": "ALT3.ASPMX.L.GOOGLE.COM", "priority": 10, "proxied": False},
        {"type": "MX", "name": "@", "content": "ALT4.ASPMX.L.GOOGLE.COM", "priority": 10, "proxied": False},
        
        # SPF TXT Record
        {"type": "TXT", "name": "@", "content": "v=spf1 include:_spf.google.com ~all", "proxied": False},
        
        # DKIM TXT Record - with static prefix and random characters for key part
        {"type": "TXT", "name": "google_domainkey", "content": "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAiKDHvtdR3aPx8e3ZlefLwShZr2vzMhg8LIXP8pFUWixHC+IwGM818ygEMDNNdv8Fv813e7M5EjmHQT9MtsGS8dLTMyPCK0atzrk2ZyIa9AArClj1IYiSQVfXCQBQYu8dQiIE9Bfi8aSt4E7AuRby/jViSDtLSLemyqKR4GAA4KtB4nVVpMmJT4ZzwfEfUHBRrQbXIMQwvumh46RCoStKC5qe3FRC2DvA/hp7RfhasXlzFfubpE1dfy7xKGm2npKtUW7r7Hnn96Lv//kLiQnBQY82hcxvdBrQHM9ORcblx7adxElVB6f2yp2lldqL2oS9fU3HkC7bUU25XXY21YqF1wIDAQAB", "proxied": False},
        
        # DMARC TXT Record - with static prefix and random domain
        {"type": "TXT", "name": "_dmarc", "content": f"v=DMARC1; p=none; rua=mailto:dmarc@{generate_random_domain()}", "proxied": False},
        
        # Google site verification - with static prefix and random string matching length
        {"type": "TXT", "name": "@", "content": f"google-site-verification={generate_random_verification_string()}", "proxied": False}
    ]
    
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for record in additional_records:
            record_name = record["name"] if record["name"] != "@" else domain
            
            # Special handling for MX records which have a priority
            if record["type"] == "MX":
                futures.append(
                    executor.submit(
                        create_mx_record,
                        login, api_key, zone_id, 
                        record_name, record["content"], record["priority"]
                    )
                )
            else:
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
                proxied_status = "Proxied" if result.get('result', {}).get('proxied', False) else "Unproxied"
                success_msg = f"DNS record {record_name} -> {record_content} added ({proxied_status})"
                if log:
                    log.append(success_msg)
            except Exception as e:
                errors.append(str(e))
                if log:
                    log.append(f"Error: {str(e)}")
    
    return len(errors) == 0

def create_mx_record(login, api_key, zone_id, name, content, priority):
    """Create an MX record with priority"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    data = {
        "type": "MX",
        "name": name,
        "content": content,
        "priority": priority,
        "ttl": 1,
        "proxied": False  # MX records cannot be proxied
    }
    try:
        response = requests.post(url, headers=get_headers(login, api_key), json=data)
        return response.json()
    except Exception as e:
        logger.error(f"Error creating MX record {name} -> {content} (priority {priority}): {str(e)}")
        return {"success": False, "error": str(e)}

def generate_random_domain():
    """Generate a realistic-looking random domain for DMARC record"""
    # Common prefixes and words used in domain names
    prefixes = ["my", "web", "cloud", "cyber", "digital", "tech", "smart", "quick", "easy", "best", 
               "pro", "top", "prime", "fast", "net", "online", "go", "get", "the", "global"]
    
    # Common words used in domain names
    words = ["site", "host", "web", "tech", "soft", "data", "blog", "app", "mail", "cloud", 
            "store", "shop", "market", "team", "tools", "hub", "zone", "spot", "space", "box",
            "work", "group", "base", "point", "net", "systems", "software", "solutions"]
    
    # Randomly decide on structure (prefix+word, word+word, or just word)
    structure = random.randint(1, 3)
    
    if structure == 1:
        # prefix + word (e.g., mycloud)
        domain_name = random.choice(prefixes) + random.choice(words)
    elif structure == 2:
        # word + word (e.g., cloudspace)
        domain_name = random.choice(words) + random.choice(words)
    else:
        # single word with optional number (e.g., cloud365)
        domain_name = random.choice(words)
        # Add a number 30% of the time
        if random.random() < 0.3:
            domain_name += str(random.randint(1, 999))
    
    # Add .com extension
    return f"{domain_name}.com"

def generate_random_verification_string():
    """Generate a random verification string matching the example length"""
    # The example string is: G8XgjG-VV894J7gNnjJTHe8MO2cXZCvIldjZzo4FoTx (43 chars)
    chars = string.ascii_letters + string.digits + "-_"
    return ''.join(random.choice(chars) for _ in range(43))

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
    import random
    
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
    
    # Send initial progress message
    progress_message = bot.send_message(
        chat_id, 
        f"⚙️ Working with account: {login}\n👨‍💻 Preparation:\n[░░░░░░░░░░] 0%\n🔄 Processed 0/{len(domains)} domains"
    )
    message_id = progress_message.message_id
    
    # Process each domain
    for index, domain in enumerate(domains):
        logger.info(f"Processing domain {domain} for account {login}")
        update_progress_message(chat_id, message_id, index, len(domains), login, "Checking domain")
        
        try:
            # Check if zone already exists
            existing_zone_id = check_zone_exists(login, api_key, domain)
            if existing_zone_id:
                zone_info[domain] = existing_zone_id
            else:
                # Create new zone
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

            # Apply DNS configuration based on type
            dns_success = False
            if dns_config_type == 1:
                dns_success = setup_dns_config_type_1(login, api_key, zone_info[domain], domain, ip_api_cdn, ip_www, log_messages)
            elif dns_config_type == 2:
                dns_success = setup_dns_config_type_2(login, api_key, zone_info[domain], domain, ip_www, log_messages)
            elif dns_config_type == 3:
                dns_success = setup_dns_config_type_3(login, api_key, zone_info[domain], domain, ip_api_cdn, ip_www, log_messages)
                
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
    
    # Get nameservers for summary
    ns_servers = []
    for domain, zone_id in zone_info.items():
        servers = get_nameservers(login, api_key, zone_id)
        if servers:
            ns_servers = servers
            break 
    
    # Prepare account info summary
    account_info = {
        "login": login,
        "ns_servers": ns_servers,
        "errors": errors,
        "domains": list(zone_info.keys())  
    }
    all_accounts_info.append(account_info)
    
    # Delete progress message
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
    chat_id = message.chat.id

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
    
    # Проверяем, есть ли активная задача
    with task_lock:
        is_processing = current_processing
    
    # Добавляем задачу в очередь
    task_queue.put((user_id, chat_id, text, message.message_id))
    
    position = task_queue.qsize()
    
    # Если уже есть активная задача или в очереди есть другие задачи, сообщаем о ждущем статусе
    if is_processing or position > 1:
        # Сохраняем информацию о сообщении пользователя
        if user_id not in waiting_users:
            waiting_users[user_id] = {}
        waiting_users[user_id][message.message_id] = time.time()
        
        wait_message = f"⏳ Ваша задача добавлена в очередь (позиция: {position}). Пожалуйста, ожидайте."
        bot.reply_to(message, wait_message)
    else:
        # Если очередь была пуста, сообщаем что задача сразу начала выполняться
        bot.reply_to(message, "✅ Ваша задача начала обрабатываться.")

# Функция для проверки статуса очереди
@bot.message_handler(commands=['status'])
def check_queue_status(message):
    user_id = message.from_user.id
    
    if not check_access(user_id):
        bot.reply_to(message, f"You don't have access to this bot. Contact admin {SUPER_ADMIN_TAG}.")
        return
    
    with task_lock:
        is_processing = current_processing
    
    queue_size = task_queue.qsize()
    
    if is_processing:
        status = "⚙️ Бот сейчас обрабатывает задачу."
    else:
        status = "✅ Бот не занят в данный момент."
    
    if queue_size > 0:
        status += f"\n📋 Задач в очереди: {queue_size}"
    else:
        status += "\n📋 Очередь пуста."
    
    if user_id in waiting_users and waiting_users[user_id]:
        status += f"\n⏳ У вас {len(waiting_users[user_id])} задач в очереди."
    
    bot.reply_to(message, status)

# Функция для обработки задач в очереди
def task_processor():
    global current_processing
    
    while True:
        try:
            # Получаем задачу из очереди
            task = task_queue.get()
            
            if task is None:  # Сигнал для завершения потока
                task_queue.task_done()
                break
                
            with task_lock:
                current_processing = True
            
            # Распаковываем данные задачи
            user_id, chat_id, text, message_id = task
            
            logger.info(f"Starting queued task for user {user_id}")
            
            # Уведомляем пользователя, что его задача начала выполняться
            try:
                if message_id in waiting_users.get(user_id, {}):
                    del waiting_users[user_id][message_id]
                    
                bot.send_message(
                    chat_id, 
                    "✅ Ваша задача началась обрабатываться."
                )
            except Exception as e:
                logger.error(f"Error sending start notification: {str(e)}")
            
            # Выполняем обработку задачи
            try:
                accounts = parse_input_text(text)
                
                if not accounts:
                    bot.send_message(chat_id, "❌ Could not recognize data format. Check your input.")
                    continue
                
                all_accounts_info = []
                
                for account in accounts:
                    time.sleep(2)
                    setup_zones(account, chat_id, all_accounts_info)
                
                send_final_summary(chat_id, all_accounts_info)
                
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                logger.error(traceback.format_exc())
                bot.send_message(chat_id, f"❌ Error processing data: {str(e)}")
            
            finally:
                # Отмечаем задачу как выполненную
                task_queue.task_done()
                
                with task_lock:
                    current_processing = False
                
                logger.info(f"Completed task for user {user_id}, queue size: {task_queue.qsize()}")
                
        except Exception as e:
            logger.error(f"Error in task processor: {str(e)}")
            logger.error(traceback.format_exc())
            time.sleep(5)  # Пауза перед следующей попыткой

# Функция для инициализации обработчика очереди
def init_task_queue():
    # Запускаем поток обработки задач
    processor_thread = threading.Thread(target=task_processor, daemon=True)
    processor_thread.start()
    logger.info("Task queue processor started")
    return processor_thread

# Измененный основной блок
if __name__ == "__main__":
    logger.info("=== BOT STARTING ===")
    logger.info(f"Current whitelist: {WHITELIST}")
    
    # Инициализируем обработчик очереди
    queue_thread = init_task_queue()
    
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
        # Отправляем сигнал для остановки потока обработки
        task_queue.put(None)
        queue_thread.join(timeout=5)
    except Exception as e:
        logger.critical(f"Critical error: {str(e)}")
        logger.critical(traceback.format_exc())
    finally:
        # Убедимся, что поток обработки остановлен
        task_queue.put(None)
        queue_thread.join(timeout=5)
        logger.info("=== BOT SHUTDOWN ===")