"""Canonical contract v1 catalogue. No implicit grants or runtime adapters."""
from dataclasses import dataclass

CATALOG_VERSION = "permissions-v3"


@dataclass(frozen=True)
class PermissionDescriptor:
    key: str
    group: str
    label_vi: str
    description_vi: str
    grantable_to_staff: bool = True
    required_with: tuple[str, ...] = ()
    exposure: str = "ordinary"


_GROUPS = (
    ("History", "calendar.read calendar.write usage.history.read usage.history.write purchase.history.read purchase.history.write"),
    ("Catalog/Menu", "ingredient.read ingredient.create menu.read product.create recipe.read recipe.create_version recipe.manage_effectivity"),
    ("Kho", "inventory.read inventory.receive inventory.count.correct procurement.cost.read"),
    ("Sales", "sales.read sales.record sales.correct sales.merge"),
    ("Supplier", "supplier.read supplier.create supplier.terms.create supplier.terms.correct supplier.fees.manage"),
    ("Import", "import.create import.upload import.read import.analyze import.preview import.commit mapping.read mapping.propose"),
    ("Planning", "planning.context.read planning.run planning.result.read planning.requirements.read planning.requirements.create planning.requirements.manage planning.export"),
    ("Budget", "budget.read budget.update"),
)
_LABELS = {
    "calendar.read": "Xem lịch nghiệp vụ", "calendar.write": "Ghi lịch nghiệp vụ",
    "usage.history.read": "Xem lịch sử sử dụng", "usage.history.write": "Ghi lịch sử sử dụng",
    "purchase.history.read": "Xem lịch sử mua", "purchase.history.write": "Ghi lịch sử mua",
    "ingredient.read": "Xem nguyên liệu", "ingredient.create": "Tạo nguyên liệu",
    "menu.read": "Xem menu và giá bán", "product.create": "Tạo món",
    "recipe.read": "Xem công thức", "recipe.create_version": "Tạo phiên bản công thức",
    "recipe.manage_effectivity": "Quản lý hiệu lực công thức",
    "inventory.read": "Xem kho", "inventory.receive": "Ghi nhận hàng nhận",
    "inventory.count.correct": "Điều chỉnh kiểm kê lô", "procurement.cost.read": "Xem giá mua và phí",
    "sales.read": "Xem doanh số", "sales.record": "Ghi doanh số", "sales.correct": "Sửa doanh số", "sales.merge": "Gộp doanh số",
    "supplier.read": "Xem nhà cung cấp", "supplier.create": "Tạo nhà cung cấp",
    "supplier.terms.create": "Tạo điều kiện cung ứng", "supplier.terms.correct": "Sửa điều kiện cung ứng", "supplier.fees.manage": "Quản lý phí giao",
    "import.create": "Tạo bản nhập", "import.upload": "Tải dữ liệu", "import.read": "Xem bản nhập",
    "import.analyze": "Phân tích dữ liệu", "import.preview": "Xem trước nhập", "import.commit": "Xác nhận nhập",
    "mapping.read": "Xem ánh xạ", "mapping.propose": "Đề xuất ánh xạ",
    "planning.context.read": "Xem thiết lập planning", "planning.run": "Chạy planning", "planning.result.read": "Xem kết quả planning",
    "planning.requirements.read": "Xem yêu cầu", "planning.requirements.create": "Lưu yêu cầu", "planning.requirements.manage": "Quản lý yêu cầu đã lưu", "planning.export": "Xuất kế hoạch",
    "budget.read": "Xem ngân sách", "budget.update": "Đổi trần ngân sách",
}
CATALOGUE = tuple(PermissionDescriptor(
    key, group, _LABELS[key], _LABELS[key] + "; chỉ trong Store được cấp quyền.",
    exposure="cost" if key == "procurement.cost.read" else "budget" if key.startswith("budget.") else "ordinary",
) for group, keys in _GROUPS for key in keys.split())
PERMISSIONS = frozenset(p.key for p in CATALOGUE)


def effective_permissions(role: str, grants: tuple[str, ...]) -> tuple[str, ...]:
    if role == "OWNER":
        return tuple(sorted(PERMISSIONS))
    if role != "STAFF" or not set(grants) <= PERMISSIONS or len(grants) != len(set(grants)):
        raise ValueError("Invalid persisted authorization data")
    return tuple(sorted(grants))
