# Phần mềm Đăng ký nhu cầu vật tư - FastAPI

## Chạy thử
```bat
run.bat
```

Truy cập: http://127.0.0.1:5010

Tài khoản mặc định:
- `admin`
- `Admin@123`

## Chức năng chính
- Đăng ký tài khoản, Admin phê duyệt user.
- Phân quyền đơn giản theo đơn vị và vai trò.
- Danh mục vật tư, import Excel.
- Lập phiếu nhu cầu theo tháng.
- Vật tư ngoài danh mục.
- Gửi Trưởng đơn vị hoặc gửi thẳng Bộ phận tổng hợp.
- Điều chỉnh gửi lại thẳng Bộ phận tổng hợp.
- Copy phiếu tháng trước sang tháng sau.
- Bộ phận tổng hợp xem/tổng hợp toàn bộ, đơn vị chỉ thấy phiếu của đơn vị mình.
- Xuất PDF phiếu, xuất Excel tổng hợp.

## Mẫu import danh mục vật tư
Các cột:
- Mã vật tư
- Tên vật tư
- Đơn vị tính
- Loại vật tư
- Nhóm vật tư
- Quy cách
- Ghi chú
