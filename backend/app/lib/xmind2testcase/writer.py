import json
import uuid
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from .metadata import TestSuite, TestCase, TestStep

def gen_id():
    return str(uuid.uuid4())

def get_xmind_zen_content(testsuites):
    """
    Convert testsuites to XMind Zen content.json structure.
    Expects a list of TestSuite objects (usually one root sheet).
    """
    sheets = []
    
    # If list is empty or just one root suite, treat as one sheet
    # XMind usually has one map per file unless multiple sheets.
    # We will put all testsuites as Main Topics under one Central Topic if multiple,
    # or if single root suite, use it as Central Topic.
    
    root_suite = None
    if len(testsuites) == 1:
        root_suite = testsuites[0]
    else:
        root_suite = TestSuite()
        root_suite.name = "Test Plan"
        root_suite.sub_suites = testsuites
    
    sheet = {
        "id": gen_id(),
        "title": "Canvas 1",
        "rootTopic": suite_to_topic(root_suite, is_root=True)
    }
    sheets.append(sheet)
    return sheets

def suite_to_topic(suite, is_root=False):
    topic = {
        "id": gen_id(),
        "title": suite.name,
        "children": {
            "attached": []
        }
    }
    
    # Structure Class (Logic right for root)
    if is_root:
        topic["structureClass"] = "org.xmind.ui.logic.right"

    # Sub Suites
    if suite.sub_suites:
        for sub in suite.sub_suites:
            topic["children"]["attached"].append(suite_to_topic(sub))
            
    # Test Cases
    if suite.testcase_list:
        for case in suite.testcase_list:
            topic["children"]["attached"].append(case_to_topic(case))
            
    # Clean up empty children
    if not topic["children"]["attached"]:
        del topic["children"]
        
    return topic

def case_to_topic(case):
    topic = {
        "id": gen_id(),
        "title": case.name,
        "children": {
            "attached": []
        }
    }
    
    # Add Priority Marker
    if case.importance:
        try:
            p = int(case.importance)
            topic["markers"] = [
                {"markerId": f"priority-{p}"}
            ]
        except:
            pass

    # Add Labels (for automation binding)
    labels = []
    if case.tc_id:
        labels.append(case.tc_id)
    if case.execution_type == 2:
        labels.append("自动")
    elif case.execution_type == 1:
        labels.append("手动")
    
    if labels:
        topic["labels"] = labels
    
    # Steps
    if case.steps:
        for step in case.steps:
            topic["children"]["attached"].append(step_to_topic(step))
            
    if not topic["children"]["attached"]:
        del topic["children"]
        
    return topic

def step_to_topic(step):
    # Step Action
    topic = {
        "id": gen_id(),
        "title": step.actions,
        "children": {
            "attached": []
        }
    }
    
    # Expected Result
    if step.expectedresults:
        expected_topic = {
            "id": gen_id(),
            "title": step.expectedresults
        }
        topic["children"]["attached"].append(expected_topic)
        
    if not topic["children"]["attached"]:
        del topic["children"]
        
    return topic

def write_xmind_zip(testsuites):
    """
    Generate XMind file bytes from testsuites.
    """
    content = get_xmind_zen_content(testsuites)
    json_str = json.dumps(content)
    
    # Create simple metadata and manifest just in case, though content.json is usually enough for Zen
    # Actually 'manifest.json' is required by some readers.
    manifest = {
        "file-entries": {
            "content.json": {},
            "metadata.json": {}
        }
    }
    
    metadata = {}

    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as zf:
        zf.writestr('content.json', json_str)
        zf.writestr('manifest.json', json.dumps(manifest))
        zf.writestr('metadata.json', json.dumps(metadata))
        
    out.seek(0)
    return out
