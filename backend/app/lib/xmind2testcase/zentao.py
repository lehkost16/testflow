#!/usr/bin/env python
# _*_ coding:utf-8 _*_
import csv
import logging
import os

from xmind2testcase.utils import get_absolute_path, get_xmind_testcase_list

"""
Convert XMind fie to Zentao testcase csv file

Zentao official document about import CSV testcase file: https://www.zentao.net/book/zentaopmshelp/243.mhtml
"""


def xmind_to_zentao_csv_file(xmind_file, testcases=None, case_type=None, apply_phase=None):
    """Convert XMind file to a zentao csv file"""
    xmind_file = get_absolute_path(xmind_file)
    logging.info("Start converting XMind file(%s) to zentao file...", xmind_file)
    
    if testcases is None:
        testcases = get_xmind_testcase_list(xmind_file)

    fileheader = [
        "所属模块",
        "用例名称",
        "前置条件",
        "步骤",
        "预期",
        "关键词",
        "优先级",
        "用例类型",
        "适用阶段",
    ]
    zentao_testcase_rows = [fileheader]
    for testcase in testcases:
        row = gen_a_testcase_row(testcase, case_type=case_type, apply_phase=apply_phase)
        zentao_testcase_rows.append(row)

    zentao_file = xmind_file[:-6] + ".csv"
    if os.path.exists(zentao_file):
        os.remove(zentao_file)
        # logging.info('The zentao csv file already exists, return it directly: %s', zentao_file)
        # return zentao_file

    with open(zentao_file, "w", encoding="utf8") as f:
        writer = csv.writer(f)
        writer.writerows(zentao_testcase_rows)
        logging.info(
            "Convert XMind file(%s) to a zentao csv file(%s) successfully!",
            xmind_file,
            zentao_file,
        )

    return zentao_file


def gen_a_testcase_row(testcase_dict, case_type=None, apply_phase=None):
    case_module = gen_case_module(testcase_dict["suite"])
    case_title = testcase_dict["name"]
    case_precontion = testcase_dict["preconditions"]
    case_step, case_expected_result = gen_case_step_and_expected_result(
        testcase_dict["steps"]
    )
    case_keyword = ""
    case_priority = gen_case_priority(testcase_dict["importance"])
    case_type = case_type or gen_case_type(testcase_dict["execution_type"])
    case_apply_phase = apply_phase or gen_case_apply_phase(testcase_dict["importance"])
    row = [
        case_module,
        case_title,
        case_precontion,
        case_step,
        case_expected_result,
        case_keyword,
        case_priority,
        case_type,
        case_apply_phase,
    ]
    return row


def gen_case_module(module_name):
    if module_name:
        module_name = module_name.replace("（", "(")
        module_name = module_name.replace("）", ")")
    else:
        module_name = "/"
    return module_name


def gen_case_step_and_expected_result(steps):
    case_step = ""
    case_expected_result = ""

    for step_dict in steps:
        case_step += (
            str(step_dict["step_number"])
            + ". "
            + step_dict["actions"].replace("\n", "").strip()
            + "\n"
        )
        case_expected_result += (
            str(step_dict["step_number"])
            + ". "
            + step_dict["expectedresults"].replace("\n", "").strip()
            + "\n"
            if step_dict.get("expectedresults", "")
            else ""
        )

    return case_step, case_expected_result


def gen_case_priority(priority):
    mapping = {1: "高", 2: "中", 3: "低"}
    if priority in mapping.keys():
        return mapping[priority]
    else:
        return 2


def gen_case_apply_phase(priority):
    mapping = {
        1: "冒烟测试阶段",
        2: "功能测试阶段",
        3: "功能测试阶段",
        4: "功能测试阶段",
    }
    if priority in mapping.keys():
        return mapping[priority]
    else:
        return 2


def gen_case_type(case_type):
    mapping = {1: "功能测试", 2: "接口测试"}
    if case_type in mapping.keys():
        return mapping[case_type]
    else:
        return "功能测试"


if __name__ == "__main__":
    xmind_file = "../docs/zentao_testcase_template.xmind"
    zentao_csv_file = xmind_to_zentao_csv_file(xmind_file)
    print("Conver the xmind file to a zentao csv file succssfully: %s", zentao_csv_file)
