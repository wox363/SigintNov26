#!/usr/bin/env python3
"""
Backend API Testing for IPDR/CDR Intelligence Analysis System
Tests the major parser overhaul with 5 different PDF formats
"""

import requests
import json
import sys
import time
from datetime import datetime

class IPDRCDRTester:
    def __init__(self, base_url="https://connection-scout-4.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.case_id = None
        self.upload_ids = []
        
    def log(self, message):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        headers = {}
        if data and not files:
            headers['Content-Type'] = 'application/json'
            
        self.tests_run += 1
        self.log(f"🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    response = requests.post(url, data=data, files=files)
                else:
                    response = requests.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
                
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ {name} - Status: {response.status_code}")
                try:
                    return success, response.json() if response.content else {}
                except:
                    return success, {}
            else:
                self.log(f"❌ {name} - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json().get('detail', 'No detail')
                    self.log(f"   Error: {error_detail}")
                except:
                    self.log(f"   Response: {response.text[:200]}")
                return False, {}
                
        except Exception as e:
            self.log(f"❌ {name} - Error: {str(e)}")
            return False, {}
    
    def create_test_case(self):
        """Create a test case with 3 subjects: Arif, Nazar, Shahnaza"""
        case_data = {
            "name": f"IPDR_CDR_Test_Case_{int(time.time())}",
            "description": "Test case for major parser overhaul - 5 PDF formats",
            "subjects": [
                {"name": "Arif"},
                {"name": "Nazar"}, 
                {"name": "Shahnaza"}
            ]
        }
        
        success, response = self.run_test(
            "Create Test Case",
            "POST", 
            "cases",
            200,  # Backend returns 200, not 201
            data=case_data
        )
        
        if success:
            self.case_id = response.get('id')
            self.log(f"📁 Created case ID: {self.case_id}")
            return True
        return False
    
    def upload_pdf(self, pdf_path, subject_name, data_type, expected_records_min=None):
        """Upload a PDF file and verify record count"""
        try:
            with open(pdf_path, 'rb') as f:
                files = {'file': f}
                data = {
                    'subject_name': subject_name,
                    'data_type': data_type,
                    'password': 'cms@13rr'
                }
                
                success, response = self.run_test(
                    f"Upload {pdf_path.split('/')[-1]}",
                    "POST",
                    f"cases/{self.case_id}/upload",
                    200,
                    data=data,
                    files=files
                )
                
                if success:
                    records_parsed = response.get('records_parsed', 0)
                    upload_id = response.get('upload_id')
                    if upload_id:
                        self.upload_ids.append(upload_id)
                    
                    self.log(f"📊 Parsed {records_parsed} records from {pdf_path.split('/')[-1]}")
                    
                    if expected_records_min and records_parsed < expected_records_min:
                        self.log(f"⚠️  Expected at least {expected_records_min} records, got {records_parsed}")
                        return False
                    
                    return True
                return False
                
        except Exception as e:
            self.log(f"❌ Upload failed: {str(e)}")
            return False
    
    def verify_nazar_ipdr_columns(self):
        """Verify Nazar IPDR records have correct columns with actual IP addresses"""
        success, response = self.run_test(
            "Get Case Records",
            "GET",
            f"cases/{self.case_id}/records",
            200
        )
        
        if not success:
            return False
            
        records = response.get('records', [])
        nazar_ipdr_records = [
            r for r in records 
            if r.get('subject_name') == 'Nazar' and r.get('record_type') == 'ipdr'
        ]
        
        if not nazar_ipdr_records:
            self.log("❌ No Nazar IPDR records found")
            return False
            
        self.log(f"📋 Found {len(nazar_ipdr_records)} Nazar IPDR records")
        
        # Check first few records for required columns
        required_columns = ['destination_ip', 'url', 'location', 'start_date', 'start_time']
        valid_records = 0
        
        for i, record in enumerate(nazar_ipdr_records[:5]):
            data = record.get('data', {})
            has_required = all(col in data for col in required_columns)
            
            # Check if destination_ip looks like an actual IP address
            dest_ip = data.get('destination_ip', '')
            has_valid_ip = bool(dest_ip and ('.' in dest_ip or ':' in dest_ip))
            
            if has_required and has_valid_ip:
                valid_records += 1
                self.log(f"✅ Record {i+1}: IP={dest_ip}, Platform={data.get('url', 'N/A')}")
            else:
                self.log(f"❌ Record {i+1}: Missing columns or invalid IP")
                
        success_rate = valid_records / min(len(nazar_ipdr_records), 5)
        if success_rate >= 0.8:  # 80% of records should be valid
            self.log(f"✅ Nazar IPDR column validation passed ({valid_records}/5 valid)")
            return True
        else:
            self.log(f"❌ Nazar IPDR column validation failed ({valid_records}/5 valid)")
            return False
    
    def run_analysis_and_verify(self):
        """Run analysis and verify key findings"""
        success, response = self.run_test(
            "Run Analysis",
            "POST",
            f"cases/{self.case_id}/analyze",
            200
        )
        
        if not success:
            return False
            
        analysis = response
        
        # Verify common contacts
        common_contacts = analysis.get('common_contacts', {})
        total_common = common_contacts.get('total_common_contacts', 0)
        
        self.log(f"📞 Found {total_common} common contacts")
        
        # Verify IMEI analysis
        imei_analysis = analysis.get('imei_analysis', {})
        total_imeis = imei_analysis.get('total_unique_imeis', 0)
        
        self.log(f"📱 Found {total_imeis} unique IMEIs")
        
        # Verify encrypted messaging detection
        secure_messaging = analysis.get('secure_messaging', {})
        encryption_findings = secure_messaging.get('encryption_findings', {})
        
        nazar_encryption = encryption_findings.get('Nazar', {})
        if nazar_encryption:
            platforms = nazar_encryption.get('platforms', [])
            self.log(f"🔒 Nazar encrypted messaging: {', '.join(platforms)}")
            
            # Check for Signal or Silent Phone
            encrypted_apps = ['Signal', 'Silent Phone']
            found_encrypted = any(app in platforms for app in encrypted_apps)
            if found_encrypted:
                self.log("✅ Detected Nazar's encrypted messaging apps")
                return True
            else:
                self.log("⚠️  Expected Signal/Silent Phone in Nazar's encrypted messaging")
        else:
            self.log("❌ No encrypted messaging found for Nazar")
            
        return False
    
    def cleanup(self):
        """Clean up test case"""
        if self.case_id:
            self.run_test(
                "Delete Test Case",
                "DELETE",
                f"cases/{self.case_id}",
                200
            )
            self.log(f"🗑️  Cleaned up test case {self.case_id}")

def main():
    """Main test execution"""
    tester = IPDRCDRTester()
    
    try:
        # Test 1: Create case with 3 subjects
        if not tester.create_test_case():
            tester.log("❌ Failed to create test case")
            return 1
            
        # Test 2: Upload all 5 PDFs with expected record counts
        pdf_tests = [
            ("/tmp/arif_cdr.pdf", "Arif", "cdr", 1600),
            ("/tmp/nazar_cdr.pdf", "Nazar", "cdr", 700),
            ("/tmp/shahnaza_oct_cdr.pdf", "Shahnaza", "cdr", 3200),
            ("/tmp/shahnaza_jan_cdr.pdf", "Shahnaza", "cdr", 3500),
            ("/tmp/nazar_ipdr.pdf", "Nazar", "ipdr", 15)
        ]
        
        upload_success = 0
        for pdf_path, subject, data_type, min_records in pdf_tests:
            if tester.upload_pdf(pdf_path, subject, data_type, min_records):
                upload_success += 1
                
        if upload_success < len(pdf_tests):
            tester.log(f"❌ Only {upload_success}/{len(pdf_tests)} uploads successful")
            
        # Test 3: Verify Nazar IPDR columns
        if not tester.verify_nazar_ipdr_columns():
            tester.log("❌ Nazar IPDR column verification failed")
            
        # Test 4: Run analysis and verify findings
        if not tester.run_analysis_and_verify():
            tester.log("❌ Analysis verification failed")
            
        # Print final results
        tester.log(f"\n📊 Final Results: {tester.tests_passed}/{tester.tests_run} tests passed")
        
        success_rate = tester.tests_passed / tester.tests_run if tester.tests_run > 0 else 0
        if success_rate >= 0.8:
            tester.log("🎉 Backend testing PASSED")
            return 0
        else:
            tester.log("💥 Backend testing FAILED")
            return 1
            
    except Exception as e:
        tester.log(f"💥 Test execution failed: {str(e)}")
        return 1
    finally:
        tester.cleanup()

if __name__ == "__main__":
    sys.exit(main())