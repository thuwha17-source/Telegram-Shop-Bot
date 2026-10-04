import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import web

# Lấy biến môi trường từ Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))

# Cấu hình tài khoản ngân hàng nhận tiền
BANK_ID = "vietcombank"
ACCOUNT_NO = "0123456789"
ACCOUNT_NAME = "NGUYEN VAN A"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Danh mục sản phẩm
PRODUCTS = {
    "sp1": {"name": "Gói Cơ Bản", "price": 50000},
    "sp2": {"name": "Gói Nâng Cao", "price": 100000},
    "sp3": {"name": "Gói VIP", "price": 200000},
}


@dp.message(CommandStart())
async def send_welcome(message: Message):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text=f"{item['name']} - {item['price']:,}đ",
                  callback_data=f"buy_{key}",
              )
          ]
          for key, item in PRODUCTS.items()
      ]
  )
  await message.answer(
      "👋 Chào mừng bạn đến với cửa hàng tự động!\n"
      "Vui lòng chọn gói sản phẩm bên dưới:",
      reply_markup=keyboard,
  )


@dp.callback_query(F.data.startswith("buy_"))
async def handle_buy(callback: CallbackQuery):
  product_key = callback.data.split("_")[1]
  product = PRODUCTS.get(product_key)
  if not product:
    return

  user_id = callback.from_user.id
  order_code = f"DH{user_id % 10000}{product_key.upper()}"
  amount = product["price"]

  qr_url = f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NO}-compact2.png?amount={amount}&addInfo={order_code}&accountName={ACCOUNT_NAME}"

  confirm_kb = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="✅ Tôi đã chuyển khoản",
              callback_data=f"confirm_{order_code}_{product_key}",
          )
      ]]
  )

  caption = (
      f"📦 **ĐƠN HÀNG: {order_code}**\n\n"
      f"• Sản phẩm: {product['name']}\n"
      f"• Cần thanh toán: {amount:,} VNĐ\n"
      f"• Nội dung chuyển khoản: `{order_code}`\n\n"
      f"👉 Vui lòng chuyển đúng số tiền và nội dung, sau đó bấm nút bên dưới."
  )

  await callback.message.delete()
  await callback.message.answer_photo(
      photo=qr_url, caption=caption, parse_mode="Markdown", reply_markup=confirm_kb
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("confirm_"))
async def handle_confirm(callback: CallbackQuery):
  _, order_code, product_key = callback.data.split("_")
  product = PRODUCTS.get(product_key)
  user = callback.from_user
  username = f"@{user.username}" if user.username else f"ID: {user.id}"

  admin_msg = (
      f"🔔 **CÓ ĐƠN HÀNG MỚI!**\n\n"
      f"• Mã đơn: `{order_code}`\n"
      f"• Khách hàng: {username}\n"
      f"• Gói: {product['name']}\n"
      f"• Số tiền: {product['price']:,} VNĐ"
  )
  if ADMIN_GROUP_ID != 0:
    await bot.send_message(
        chat_id=ADMIN_GROUP_ID, text=admin_msg, parse_mode="Markdown"
    )

  await callback.message.answer(
      "✅ Đã ghi nhận thông tin!\n"
      "Hệ thống sẽ đối soát chuyển khoản và phản hồi ngay."
  )
  await callback.answer()


# Khởi tạo web server giả lập cổng cho Render Free Web Service
async def handle_health(request):
  return web.Response(text="Bot is running!")


async def start_web_server():
  app = web.Application()
  app.router.add_get("/", handle_health)
  port = int(os.getenv("PORT", 8080))
  runner = web.AppRunner(app)
  await runner.setup()
  site = web.TCPSite(runner, "0.0.0.0", port)
  await site.start()


async def main():
  print("Bot đang hoạt động...")
  await start_web_server()
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())


