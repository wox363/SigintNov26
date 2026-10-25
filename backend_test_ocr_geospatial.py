import requests
import sys
import json
import os
from datetime import datetime

class OCRGeospatialTester:
    def __init__(self, base_url="https://connection-scout-4.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.case_id = None
        self.analysis_data = None

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'} if not files else {}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
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
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json() if response.content else {}
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                if response.content:
                    try:
                        error_data = response.json()
                        print(f"   Error: {error_data}")
                    except:
                        print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_create_case_with_locations(self):
        """Test case creation for geospatial testing"""
        case_data = {
            "name": f"Geospatial OCR Test {datetime.now().strftime('%H%M%S')}",
            "description": "Testing OCR preprocessing and geospatial mapping features"
        }
        success, response = self.run_test(
            "Create Case for OCR/Geospatial Testing",
            "POST",
            "cases",
            200,
            data=case_data
        )
        if success and 'id' in response:
            self.case_id = response['id']
            print(f"   Created case ID: {self.case_id}")
            return True
        return False

    def test_add_subjects_with_locations(self):
        """Test adding subjects with specific locations for geospatial testing"""
        if not self.case_id:
            print("❌ No case ID available for testing")
            return False

        subjects = [
            {"name": "Safvi", "phone": "9541476474", "imei": "356938035643809", "location": "Bemina Srinagar"},
            {"name": "Chakan", "phone": "9906123456", "imei": "352345678901234", "location": "Nowgam Sumbal"},
            {"name": "TestSubject", "phone": "9876543210", "imei": "123456789012345", "location": "Delhi"}
        ]

        all_success = True
        for subject in subjects:
            success, response = self.run_test(
                f"Add Subject {subject['name']} with location {subject['location']}",
                "POST",
                f"cases/{self.case_id}/subjects",
                200,
                data=subject
            )
            if not success:
                all_success = False

        return all_success

    def test_ocr_png_upload(self):
        """Test OCR preprocessing for PNG image upload"""
        if not self.case_id:
            print("❌ No case ID available for testing")
            return False

        test_file_path = "/app/tests/sample_ocr_test.png"
        if not os.path.exists(test_file_path):
            print(f"❌ Test file not found: {test_file_path}")
            return False

        with open(test_file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'subject_name': 'TestSubject',
                'data_type': 'cdr'
            }
            
            success, response = self.run_test(
                "OCR PNG Upload with Enhanced Preprocessing",
                "POST",
                f"cases/{self.case_id}/upload",
                200,
                data=data,
                files=files
            )
            
            if success:
                records_parsed = response.get('records_parsed', 0)
                sample_columns = response.get('sample_columns', [])
                print(f"   OCR parsed {records_parsed} records")
                print(f"   Sample columns: {sample_columns}")
                
                if records_parsed > 0:
                    print("   ✅ OCR successfully extracted tabular data from PNG")
                    return True
                else:
                    print("   ❌ OCR failed to extract records from PNG")
                    return False
            
        return False

    def test_protected_pdf_upload(self):
        """Test password-protected PDF upload"""
        if not self.case_id:
            print("❌ No case ID available for testing")
            return False

        test_file_path = "/app/tests/sample_protected.pdf"
        if not os.path.exists(test_file_path):
            print(f"❌ Test file not found: {test_file_path}")
            return False

        with open(test_file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'subject_name': 'TestSubject',
                'data_type': 'cdr',
                'password': 'test123'
            }
            
            success, response = self.run_test(
                "Password-Protected PDF Upload",
                "POST",
                f"cases/{self.case_id}/upload",
                200,
                data=data,
                files=files
            )
            
            if success:
                records_parsed = response.get('records_parsed', 0)
                sample_columns = response.get('sample_columns', [])
                print(f"   PDF parsed {records_parsed} records")
                print(f"   Sample columns: {sample_columns}")
                
                if records_parsed > 0:
                    print("   ✅ Password-protected PDF successfully parsed")
                    return True
                else:
                    print("   ❌ Password-protected PDF parsing failed")
                    return False
            
        return False

    def test_upload_location_data(self):
        """Upload CDR and IPDR data for subjects with locations"""
        if not self.case_id:
            print("❌ No case ID available for testing")
            return False

        test_files = [
            {"file_path": "/app/tests/sample_cdr_safvi.csv", "subject": "Safvi", "data_type": "cdr"},
            {"file_path": "/app/tests/sample_ipdr_safvi.csv", "subject": "Safvi", "data_type": "ipdr"},
            {"file_path": "/app/tests/sample_cdr_chakan.csv", "subject": "Chakan", "data_type": "cdr"},
            {"file_path": "/app/tests/sample_ipdr_chakan.csv", "subject": "Chakan", "data_type": "ipdr"}
        ]

        all_success = True
        for test_file in test_files:
            if not os.path.exists(test_file["file_path"]):
                print(f"❌ Test file not found: {test_file['file_path']}")
                all_success = False
                continue

            with open(test_file["file_path"], 'rb') as f:
                files = {'file': f}
                data = {
                    'subject_name': test_file["subject"],
                    'data_type': test_file["data_type"]
                }
                
                success, response = self.run_test(
                    f"Upload {test_file['data_type'].upper()} for {test_file['subject']} (Location Data)",
                    "POST",
                    f"cases/{self.case_id}/upload",
                    200,
                    data=data,
                    files=files
                )
                
                if success and 'records_parsed' in response:
                    print(f"   Parsed {response['records_parsed']} records")
                else:
                    all_success = False

        return all_success

    def test_geospatial_analysis(self):
        """Test analysis with geospatial correlation and geocoding"""
        if not self.case_id:
            print("❌ No case ID available for testing")
            return False
        
        success, response = self.run_test(
            "Run Geospatial Analysis with Geocoding",
            "POST",
            f"cases/{self.case_id}/analyze",
            200
        )
        
        if success:
            self.analysis_data = response
            
            # Check for location_correlation section
            location_correlation = response.get('location_correlation', {})
            if not location_correlation:
                print("   ❌ Missing location_correlation section")
                return False
            
            # Check for geocoded data
            geocoded = location_correlation.get('geocoded', {})
            if not geocoded:
                print("   ❌ Missing geocoded field in location_correlation")
                return False
            
            print(f"   ✅ Found geocoded data for {len(geocoded)} subjects")
            
            # Verify geocoded coordinates
            for subject, coords in geocoded.items():
                if 'lat' in coords and 'lng' in coords:
                    print(f"   ✅ {subject}: lat={coords['lat']}, lng={coords['lng']}")
                    print(f"      Location: {coords.get('location', 'N/A')}")
                    print(f"      Display: {coords.get('display', 'N/A')}")
                else:
                    print(f"   ❌ {subject}: Missing lat/lng coordinates")
                    return False
            
            # Check for distance calculations
            comparisons = location_correlation.get('comparisons', [])
            if comparisons:
                print(f"   ✅ Found {len(comparisons)} location comparisons")
                for comp in comparisons:
                    if comp.get('distance_km') is not None:
                        print(f"      Distance between {comp['subjects']}: {comp['distance_km']} km")
            
            return True
            
        return False

    def test_list_uploads_with_ocr(self):
        """Test that OCR uploads appear in upload history"""
        if not self.case_id:
            print("❌ No case ID available for testing")
            return False
        
        success, response = self.run_test(
            "List Uploads (Including OCR)",
            "GET",
            f"cases/{self.case_id}/uploads",
            200
        )
        
        if success:
            uploads = response
            print(f"   Found {len(uploads)} uploads")
            
            # Look for OCR uploads
            ocr_uploads = [u for u in uploads if u.get('data_format') in ['png', 'pdf']]
            if ocr_uploads:
                print(f"   ✅ Found {len(ocr_uploads)} OCR uploads:")
                for upload in ocr_uploads:
                    print(f"      - {upload.get('file_name')} ({upload.get('data_format')}) - {upload.get('record_count')} records")
                return True
            else:
                print("   ❌ No OCR uploads found in history")
                return False
        
        return False

def main():
    print("🚀 Starting OCR & Geospatial Features Test")
    print("=" * 60)
    
    tester = OCRGeospatialTester()
    
    # Test sequence for new features
    tests = [
        ("Create Case with Locations", tester.test_create_case_with_locations),
        ("Add Subjects with Locations", tester.test_add_subjects_with_locations),
        ("OCR PNG Upload", tester.test_ocr_png_upload),
        ("Protected PDF Upload", tester.test_protected_pdf_upload),
        ("Upload Location Data", tester.test_upload_location_data),
        ("Geospatial Analysis", tester.test_geospatial_analysis),
        ("List Uploads with OCR", tester.test_list_uploads_with_ocr),
    ]
    
    for test_name, test_func in tests:
        print(f"\n📋 Running {test_name} test...")
        try:
            success = test_func()
            if not success:
                print(f"❌ {test_name} test failed - continuing with remaining tests")
                # Don't break, continue with other tests to get full picture
        except Exception as e:
            print(f"❌ {test_name} test crashed: {str(e)}")
    
    # Print final results
    print(f"\n📊 Final Results:")
    print(f"Tests passed: {tester.tests_passed}/{tester.tests_run}")
    print(f"Success rate: {(tester.tests_passed/tester.tests_run*100):.1f}%" if tester.tests_run > 0 else "No tests run")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())