# -*- coding: utf-8 -*-

import sys
import os
import json
import time
import re
import hashlib
import subprocess
import winreg
from datetime import datetime, timedelta, timezone
from tzlocal import get_localzone
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURAÇÃO ---
MALWAREBYTES_REPORTS_PATH = r"C:\ProgramData\Malwarebytes\MBAMService\ScanResults"
KASPERSKY_PATH = r"C:\Program Files (x86)\Kaspersky Lab\Kaspersky 21.24\avp.com"

# --- VARIÁVEIS GLOBAIS ---
malwarebytes_report_data = None
kaspersky_report_content = None
kaspersky_status_content = None
kaspersky_db_last_update = "N/A"
kaspersky_client_name = "N/A"
kaspersky_version = "N/A"
stop_monitoring_mb = False

# --- LÓGICA DE CÁLCULO DE HASH E INFO DE ARQUIVO ---

def get_file_details(file_path):
    """Calculates MD5, SHA256, full name and file size."""
    print("\n--- CALCULATING FILE DETAILS ---")
    try:
        details = {
            "full_path": os.path.abspath(file_path),
            "file_name": os.path.basename(file_path),
            "file_size_bytes": os.path.getsize(file_path)
        }
        
        hash_md5 = hashlib.md5()
        hash_sha256 = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
                hash_sha256.update(chunk)
        
        details["md5"] = hash_md5.hexdigest().upper()
        details["sha256"] = hash_sha256.hexdigest().upper()
        
        print("[OK] File details calculated successfully.")
        return details
    except Exception as e:
        print(f"[ERROR] Could not retrieve file details: {e}")
        return None

# --- LÓGICA DO MALWAREBYTES (COM WATCHDOG E TENTATIVAS) ---

class MalwarebytesReportHandler(FileSystemEventHandler):
    def __init__(self, start_time):
        self.start_time = start_time
        super().__init__()

    def on_created(self, event):
        global stop_monitoring_mb
        if stop_monitoring_mb or event.is_directory or not event.src_path.endswith('.json'):
            return

        if os.path.getmtime(event.src_path) > self.start_time:
            print(f"\n[INFO] New Malwarebytes report detected: {os.path.basename(event.src_path)}")
            self.process_malwarebytes_report_with_retries(event.src_path)
            stop_monitoring_mb = True
            print("[OK] Malwarebytes report received and processed.")

    def process_malwarebytes_report_with_retries(self, path):
        global malwarebytes_report_data
        max_retries = 5
        for attempt in range(max_retries):
            try:
                time.sleep(2)
                with open(path, 'r', encoding='utf-8') as f:
                    full_content = f.read()
                
                if not full_content.strip(): raise ValueError("Report file is empty.")
                match = re.search(r'\{.*\}', full_content, re.DOTALL)
                if not match: raise ValueError("No valid JSON block found.")
                
                data = json.loads(match.group(0))
                
                source_details = data.get("sourceDetails", {})
                malwarebytes_report_data = {
                    "applicationVersion": data.get("applicationVersion", "N/A"),
                    "clientID": data.get("clientID", "N/A"),
                    "clientType": data.get("clientType", "N/A"),
                    "componentsUpdatePackageVersion": data.get("componentsUpdatePackageVersion", "N/A"),
                    "coreDllFileVersion": data.get("coreDllFileVersion", "N/A"),
                    "cpu": data.get("cpu", "N/A"),
                    "dbSDKUpdatePackageVersion": data.get("dbSDKUpdatePackageVersion", "N/A"),
                    "detectionDateTime": data.get("detectionDateTime", "N/A"),
                    "fileSystem": data.get("fileSystem", "N/A"),
                    "licenseState": data.get("licenseState", "N/A"),
                    "os": data.get("os", "N/A"),
                    "objectsScanned": source_details.get("objectsScanned", "N/A"),
                    "scanEndTime": source_details.get("scanEndTime", "N/A"),
                    "scanOnlineStatus": source_details.get("scanOnlineStatus", "N/A"),
                    "scanResult": source_details.get("scanResult", "N/A"),
                    "scanStartTime": source_details.get("scanStartTime", "N/A"),
                    "threatsDetected": data.get("threatsDetected", "N/A")
                }
                return
            except Exception as e:
                print(f"[WARNING] Attempt {attempt + 1}/{max_retries} to read Malwarebytes report failed: {e}")
        
        print("[ERROR] Could not process Malwarebytes report after several attempts.")
        malwarebytes_report_data = {"result": "Persistent Read Error"}

# --- FUNÇÕES PRINCIPAIS ---

def start_malwarebytes_monitor(start_time):
    observer_mb = Observer()
    observer_mb.schedule(MalwarebytesReportHandler(start_time), MALWAREBYTES_REPORTS_PATH, recursive=False)
    observer_mb.start()
    print("\n--- MONITORING MALWAREBYTES IN REAL TIME ---")
    print("You can start the manual Malwarebytes scan at any time.")
    return observer_mb

def get_kaspersky_db_last_update():
    global kaspersky_db_last_update
    try:
        reg_path = r"SOFTWARE\WOW6432Node\KasperskyLab\AVP21.24\Data\UpdateState"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
        filetime, _ = winreg.QueryValueEx(key, "LastUpdate")
        winreg.CloseKey(key)
        
        # Convert FILETIME to datetime in UTC
        dt = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=filetime // 10)
        # Convert to local timezone
        local_tz = get_localzone()
        dt_local = dt.astimezone(local_tz)
        kaspersky_db_last_update = dt_local.strftime("%Y-%m-%d %H:%M:%S")
        print("[OK] Kaspersky database last update date obtained: " + kaspersky_db_last_update)
    except Exception as e:
        print(f"[ERROR] Could not obtain Kaspersky database last update date: {e}")
        kaspersky_db_last_update = "N/A"

def get_kaspersky_client_info():
    global kaspersky_client_name, kaspersky_version
    try:
        # Get Product Name
        name_command = ['powershell', '-Command', f'(Get-Item "{KASPERSKY_PATH}").VersionInfo.ProductName']
        name_result = subprocess.run(name_command, capture_output=True, text=True)
        kaspersky_client_name = name_result.stdout.strip() if name_result.returncode == 0 else "N/A"
        
        # Get Product Version
        version_command = ['powershell', '-Command', f'(Get-Item "{KASPERSKY_PATH}").VersionInfo.ProductVersion']
        version_result = subprocess.run(version_command, capture_output=True, text=True)
        kaspersky_version = version_result.stdout.strip() if version_result.returncode == 0 else "N/A"
        
        print("[OK] Kaspersky client information obtained.")
    except Exception as e:
        print(f"[ERROR] Could not obtain Kaspersky client information: {e}")
        kaspersky_client_name = "N/A"
        kaspersky_version = "N/A"

def run_kaspersky_scan(file_path):
    global kaspersky_report_content, kaspersky_status_content
    
    # Verify if avp.com exists
    if not os.path.isfile(KASPERSKY_PATH):
        error_msg = f"[ERROR] avp.com file not found at: {KASPERSKY_PATH}"
        print(error_msg)
        kaspersky_report_content = error_msg
        kaspersky_status_content = "N/A"
        return
    
    print("\n--- PREPARING KASPERSKY SCAN VIA AVP.COM ---")
    print("Collecting Kaspersky information and starting scan. This may take a moment...")
    
    # Auxiliary function to execute avp.com commands
    def run_avp_command(command, command_name):
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"[OK] Kaspersky {command_name} obtained.")
                return result.stdout.strip() if result.stdout else "N/A"
            else:
                error_msg = f"Error executing {command_name}: Return code {result.returncode}, stderr: {result.stderr or 'No detailed error available.'}"
                print(f"[ERROR {command_name}] {error_msg}")
                return error_msg
        except Exception as e:
            error_msg = f"Exception executing {command_name}: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return error_msg
    
    # Execute STATUS command
    kaspersky_status_content = run_avp_command([KASPERSKY_PATH, "STATUS"], "Status")
    
    # Execute SCAN command
    report_path = os.path.join(os.path.dirname(os.path.abspath(file_path)), "Kaspersky_Report.txt")
    scan_command = [KASPERSKY_PATH, "SCAN", os.path.abspath(file_path), "/i1", "/fa", f"/RA:{report_path}"]
    kaspersky_report_content = run_avp_command(scan_command, "Scan")
    
    # Try to read the generated report, if available
    if os.path.isfile(report_path):
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                kaspersky_report_content = f.read()
            print(f"[OK] Kaspersky report read from: {report_path}")
        except Exception as e:
            print(f"[ERROR] Failed to read Kaspersky report: {e}")
            kaspersky_report_content = f"Error reading report: {str(e)}"
    return report_path  # Return the path for later deletion

def filter_kaspersky_status(status_content):
    if "N/A" in status_content or "Error" in status_content:
        return status_content
    keywords = ['Scan', 'Protection', 'Update', 'Firewall', 'Hips', 'ids', 'AMSI', 'AVStreamMonitorTask', 'File_Monitoring', 'Mail_Monitoring']
    lines = status_content.splitlines()
    filtered = [line for line in lines if any(keyword in line for keyword in keywords)]
    return "\n".join(filtered)

def format_kaspersky_report(raw_content):
    """
    Formats the Kaspersky report content to match the expected output style:
    - Settings lines: key padded with tabs to align values at column ~25
    - Statistics lines: key padded with tabs to align values
    - Removes trailing '; ------------------' line at the end of statistics
    """
    if not raw_content:
        return raw_content

    settings_align = {
        "; Action on detect:":   "\t\t",
        "; Scan objects:":       "\t\t\t",
        "; Use iChecker:":       "\t\t\t",
        "; Use iSwift:":         "\t\t\t\t",
        "; Try disinfect:":      "\t\t\t",
        "; Try delete:":         "\t\t\t\t",
        "; Try delete container:": "\t",
        "; Scan archives:":      "\t\t\t",
        "; Exclude by mask:":    "\t\t",
        "; Include by mask:":    "\t\t",
    }

    stats_align = {
        "; Processed objects:":  "\t\t",
        "; Total OK:":           "\t\t\t\t\t",
        "; Total detected:":     "\t\t\t",
        "; Suspicions:":         "\t\t\t\t",
        "; Total skipped:":      "\t\t\t",
        "; Password protected:": "\t",
        "; Corrupted:":          "\t\t\t\t",
        "; Errors:":             "\t\t\t\t\t",
    }

    lines = raw_content.splitlines()
    output_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip trailing statistics separator line
        if line.strip() in ('; ------------------', ';  ------------------'):
            i += 1
            continue

        # Apply settings alignment
        replaced = False
        for key, tabs in settings_align.items():
            if line.startswith(key):
                value = line[len(key):].strip()
                output_lines.append(f"{key}{tabs}{value}")
                replaced = True
                break

        if not replaced:
            # Apply statistics alignment
            for key, tabs in stats_align.items():
                if line.startswith(key):
                    value = line[len(key):].strip()
                    output_lines.append(f"{key}{tabs}{value}")
                    replaced = True
                    break

        if not replaced:
            output_lines.append(line)

        i += 1

    # Remove trailing blank lines from the block
    while output_lines and output_lines[-1].strip() == '':
        output_lines.pop()

    return "\n".join(output_lines)


def generate_final_report(target_file, file_details, kaspersky_report_path):
    global kaspersky_report_content, kaspersky_status_content, malwarebytes_report_data, kaspersky_db_last_update, kaspersky_client_name, kaspersky_version
    print("\n--- GENERATING FINAL REPORT ---")
    
    file_dir = os.path.dirname(target_file)
    file_name_base = os.path.splitext(os.path.basename(target_file))[0]
    report_path = os.path.join(file_dir, f"{file_name_base}_Malwarebytes-Kaspersky_Scan.txt")
    report_time = datetime.now(get_localzone()).strftime("%Y-%m-%d %H:%M:%S")
    
    filtered_status = filter_kaspersky_status(kaspersky_status_content)
    formatted_kaspersky = format_kaspersky_report(kaspersky_report_content)

    # Censor the Windows username from all paths in the report
    # Extracts username from path like C:\Users\<username>\...
    username_match = re.search(r'[Cc]:\\[Uu]sers\\([^\\]+)\\', target_file)
    def censor_username(text):
        if username_match and text:
            username = username_match.group(1)
            return text.replace(username, '[USER]')
        return text

    formatted_kaspersky = censor_username(formatted_kaspersky)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("======================================================\n")
        f.write("        SECURITY SCAN REPORT\n")
        f.write("======================================================\n")
        f.write(f"Report Date: {report_time}\n")

        f.write("------------------------------------------------------\n")
        f.write("     FILE DETAILS\n")
        f.write("------------------------------------------------------\n")
        if file_details:
            f.write(f"File Name: {file_details.get('file_name', 'N/A')}\n")
            f.write(f"Size: {file_details.get('file_size_bytes', 'N/A')} bytes\n")
            f.write(f"MD5: {file_details.get('md5', 'N/A')}\n")
            f.write(f"SHA256: {file_details.get('sha256', 'N/A')}\n")
        else:
            f.write("Could not retrieve file details.\n")

        f.write("------------------------------------------------------\n")
        f.write("  1. MALWAREBYTES SCAN (Manual Verification)\n")
        f.write("------------------------------------------------------\n")
        if malwarebytes_report_data and "Erro" not in malwarebytes_report_data.get("resultado", ""):
            for key, value in malwarebytes_report_data.items():
                formatted_key = ' '.join(re.findall('[A-Z][^A-Z]*', key.capitalize()))
                f.write(f"{formatted_key}: {value}\n")
        else:
            f.write("Result: Report not detected or processed.\n")
        f.write("\n")

        f.write("------------------------------------------------------\n")
        f.write("  2. KASPERSKY SCAN (Automated via AVP.com)\n")
        f.write("------------------------------------------------------\n")
        f.write(f"Kaspersky Client: {kaspersky_client_name}\n")
        f.write(f"Version: {kaspersky_version}\n")
        f.write(f"Last Database Update: {kaspersky_db_last_update}\n")
        if formatted_kaspersky:
            f.write("\nScan Result:\n")
            f.write(formatted_kaspersky + "\n")
        else:
            f.write("Result: Scan not executed.\n")
        if filtered_status and filtered_status != "N/A":
            f.write("\n---------------------------------------------------------------------\n")
            f.write(filtered_status + "\n")
        f.write("\n")

        f.write("======================================================\n")
        f.write("                  END OF REPORT\n")
        f.write("======================================================\n")

    print(f"[SUCCESS] Report saved at: {report_path}")
    
    # Delete the temporary Kaspersky report file
    if os.path.isfile(kaspersky_report_path):
        try:
            os.remove(kaspersky_report_path)
            print(f"[OK] Temporary Kaspersky report deleted: {kaspersky_report_path}")
        except Exception as e:
            print(f"[ERROR] Failed to delete temporary Kaspersky report {kaspersky_report_path}: {e}")

def main():
    if len(sys.argv) < 2:
        print("ERROR: Drag a file over the .bat to use.")
        time.sleep(5)
        sys.exit(1)
        
    target_file_path = sys.argv[1]
    start_time = time.time()

    file_details = get_file_details(target_file_path)
    
    mb_observer = start_malwarebytes_monitor(start_time)
    
    get_kaspersky_db_last_update()
    get_kaspersky_client_info()
    kaspersky_report_path = run_kaspersky_scan(target_file_path)
    
    print("\nWaiting for Malwarebytes monitor completion (if still running)...")
    timeout_mb = 300
    end_time = time.time() + timeout_mb
    while not stop_monitoring_mb and time.time() < end_time:
        time.sleep(1)

    if not stop_monitoring_mb:
        print("[WARNING] Timeout waiting for Malwarebytes report.")

    mb_observer.stop()
    mb_observer.join()

    generate_final_report(target_file_path, file_details, kaspersky_report_path)

if __name__ == "__main__":
    main()