"""A summary must not require inventing an issuer or publication date."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

SCHEMA = json.loads((Path(__file__).parents[1] / 'skills/cahy-kn2-tom-tat/references/s2_tom_tat.schema.json').read_text(encoding='utf-8'))


def value(level):
    data = {'so_ky_hieu': None, 'ngay_ban_hanh': None, 'co_quan_ban_hanh': None,
            'trich_yeu': 'Tài liệu kiểm thử ghi mã QA-UPLOAD-261023-321d948.',
            'thoi_han': [], 'nhiem_vu_cong_an': []}
    if level == 'tom_tat_ngan':
        data.update(y_chinh=['Đây là tài liệu kiểm thử.', 'Tài liệu không phải hồ sơ nghiệp vụ.',
                             'Mã đối chiếu QA-UPLOAD-261023-321d948.'],
                    de_xuat_xu_ly='Tài liệu không nêu đề xuất xử lý.')
    if level == 'tom_tat_chi_tiet':
        data['noi_dung_theo_phan'] = [{'phan': 'Nội dung', 'noi_dung': 'Mã QA-UPLOAD-261023-321d948.'}]
    return data


@pytest.mark.parametrize('level', ['tom_tat_trich_yeu', 'tom_tat_ngan', 'tom_tat_chi_tiet'])
def test_unknown_metadata_can_remain_null(level):
    Draft202012Validator({'$ref': '#/$defs/' + level, '$defs': SCHEMA['$defs']}).validate(value(level))


@pytest.mark.parametrize('field,bad', [('ngay_ban_hanh', '23/10/2026'), ('co_quan_ban_hanh', '')])
def test_present_metadata_keeps_existing_validation(field, bad):
    data = value('tom_tat_ngan')
    data[field] = bad
    with pytest.raises(ValidationError):
        Draft202012Validator({'$ref': '#/$defs/tom_tat_ngan', '$defs': SCHEMA['$defs']}).validate(data)
