import asyncio
import json
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))

# Thông tin tài khoản ngân hàng nhận tiền
BANK_ID = "mbbank"
ACCOUNT_NO = "0929388991"
ACCOUNT_NAME = "NGUYEN HA ANH THU"

DB_FILE = "users_db.json"


def load_db():
  if os.path.exists(DB_FILE):
    try:
      with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return {}
  return {}


def save_db(data):
  with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


db = load_db()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class DepositState(StatesGroup):
  waiting_amount = State()


PRODUCTS = {
    "zin": {"name": "Loại 1: Zin", "price": 4500},
    "da": {"name": "Loại 2: Đá", "price": 3500},
    "ac_new": {"name": "Loại 3: Ac New", "price": 5500},
    "tt_chualuu": {"name": "TikTok: Chưa lưu mã", "price": 3500},
    "tt_luusan": {"name": "TikTok: Lưu sẵn mã", "price": 4000},
}


def get_main_menu(user_id: int):
  balance = db.get(str(user_id), 0)
  buttons = []
  for key, item in PRODUCTS.items():
    buttons.append([
        InlineKeyboardButton(
            text=f"🛒 {item['name']} - {item['price']:,}đ",
            callback_data=f"buy_{key}",
        )
    ])
  buttons.append(
      [InlineKeyboardButton(text="💳 Nạp tiền vào tài khoản", callback_data="topup")]
  )
  text = (
      f"👋 **CHÀO MỪNG ĐẾN SHOP TÀI KHOẢN**\n\n"
      f"💰 **Số dư hiện tại:** `{balance:,} VNĐ`\n\n"
      f"👇 Chọn loại tài khoản cần mua hoặc nạp thêm tiền:"
  )
  return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def send_welcome(message: Message, state: FSMContext):
  await state.clear()
  user_id = str(message.from_user.id)
  if user_id not in db:
    db[user_id] = 0
    save_db(db)
  text, kb = get_main_menu(message.from_user.id)
  await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data == "back_home")
async def back_home_handler(callback: CallbackQuery, state: FSMContext):
  await state.clear()
  text, kb = get_main_menu(callback.from_user.id)
  try:
    await callback.message.delete()
  except Exception:
    pass
  await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
  await callback.answer()


@dp.callback_query(F.data == "topup")
async def topup_handler(callback: CallbackQuery, state: FSMContext):
  await state.set_state(DepositState.waiting_amount)
  cancel_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="❌ Hủy bỏ", callback_data="back_home")]
      ]
  )
  await callback.message.answer(
      "💳 **NẠP TIỀN VÀO TÀI KHOẢN**\n\n"
      "• Hạn mức tối thiểu: **10.000 VNĐ**\n"
      "👉 Vui lòng nhập số tiền muốn nạp (ví dụ: `20000` hoặc `50000`):",
      reply_markup=cancel_kb,
      parse_mode="Markdown",
  )
  await callback.answer()


@dp.message(DepositState.waiting_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
  content = message.text.replace(".", "").replace(",", "").strip()
  if not content.isdigit():
    await message.answer("⚠️ Vui lòng chỉ nhập số tiền (ví dụ: `20000`):")
    return

  amount = int(content)
  if amount < 10000:
    await message.answer(
        "⚠️ Mức nạp tối thiểu là **10.000 VNĐ**. Vui lòng nhập lại số tiền:"
    )
    return

  await state.clear()
  user_id = message.from_user.id
  code = f"NAP{user_id % 100000}"

  qr_url = f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NO}-compact2.png?amount={amount}&addInfo={code}&accountName={ACCOUNT_NAME}"

  confirm_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Tôi đã chuyển khoản",
                  callback_data=f"paid_{user_id}_{amount}_{code}",
              )
          ],
          [InlineKeyboardButton(text="Quay lại Menu", callback_data="back_home")],
      ]
  )

  caption = (
      f"💳 **LỆNH NẠP TIỀN: {code}**\n\n"
      f"• Ngân hàng: **MBBank**\n"
      f"• STK: `{ACCOUNT_NO}`\n"
      f"• Chủ TK: **{ACCOUNT_NAME}**\n"
      f"• Số tiền: **{amount:,} VNĐ**\n"
      f"• Nội dung chuyển khoản: `{code}`\n\n"
      f"👉 Vui lòng chuyển đúng số tiền và nội dung, sau đó bấm nút **Tôi đã chuyển khoản** bên dưới."
  )
  await message.answer_photo(
      photo=qr_url, caption=caption, reply_markup=confirm_kb, parse_mode="Markdown"
  )


@dp.callback_query(F.data.startswith("paid_"))
async def handle_paid(callback: CallbackQuery):
  _, uid_str, amt_str, code = callback.data.split("_")
  amount = int(amt_str)
  user = callback.from_user
  username = f"@{user.username}" if user.username else f"ID: {user.id}"

  admin_kb = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text=f"✅ Duyệt nạp +{amount:,}đ",
              callback_data=f"approve_{uid_str}_{amount}",
          )
      ]]
  )

  admin_msg = (
      f"🔔 **YÊU CẦU NẠP TIỀN MỚI!**\n\n"
      f"• Khách hàng: {username}\n"
      f"• Mã nạp: `{code}`\n"
      f"• Số tiền: **{amount:,} VNĐ**\n\n"
      f"👉 Kiểm tra app MBBank, nếu đã nhận tiền hãy bấm duyệt bên dưới:"
  )

  if ADMIN_GROUP_ID != 0:
    await bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=admin_msg,
        reply_markup=admin_kb,
        parse_mode="Markdown",
    )

  await callback.message.answer(
      "✅ Đã gửi yêu cầu nạp tiền! Vui lòng chờ admin kiểm tra và cộng số dư."
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("approve_"))
async def approve_topup(callback: CallbackQuery):
  _, uid_str, amt_str = callback.data.split("_")
  amount = int(amt_str)

  current_bal = db.get(uid_str, 0)
  db[uid_str] = current_bal + amount
  save_db(db)

  await callback.message.edit_text(
      f"{callback.message.text}\n\n🟢 **ĐÃ DUYỆT BỞI:** @{callback.from_user.username or callback.from_user.first_name}"
  )

  try:
    await bot.send_message(
        chat_id=int(uid_str),
        text=(
            f"🎉 **NẠP TIỀN THÀNH CÔNG!**\n\n"
            f"• Số tiền cộng: `+{amount:,} VNĐ`\n"
            f"• Số dư mới: `{db[uid_str]:,} VNĐ`\n\n"
            f"Gõ /start để tiếp tục mua hàng!"
        ),
        parse_mode="Markdown",
    )
  except Exception:
    pass

  await callback.answer("Đã duyệt cộng tiền thành công!")


@dp.callback_query(F.data.startswith("buy_"))
async def handle_buy(callback: CallbackQuery):
  product_key = callback.data.split("_", 1)[1]
  product = PRODUCTS.get(product_key)
  if not product:
    return

  user_id = str(callback.from_user.id)
  current_bal = db.get(user_id, 0)
  price = product["price"]

  if current_bal < price:
    topup_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Nạp tiền ngay", callback_data="topup"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Quay lại Menu", callback_data="back_home"
                )
            ],
        ]
    )
    await callback.message.answer(
        f"❌ **Số dư không đủ!**\n\n"
        f"• Giá mặt hàng: `{price:,} VNĐ`\n"
        f"• Số dư ví: `{current_bal:,} VNĐ`\n\n"
        f"Vui lòng nạp thêm tiền để mua hàng:",
        reply_markup=topup_kb,
        parse_mode="Markdown",
    )
    await callback.answer()
    return

  db[user_id] = current_bal - price
  save_db(db)

  user = callback.from_user
  username = f"@{user.username}" if user.username else f"ID: {user.id}"

  if ADMIN_GROUP_ID != 0:
    admin_msg = (
        f"🛍 **ĐƠN MUA HÀNG THÀNH CÔNG!**\n\n"
        f"• Khách hàng: {username}\n"
        f"• Mặt hàng: {product['name']}\n"
        f"• Trừ tiền ví: -{price:,} VNĐ\n"
        f"• Số dư còn lại: {db[user_id]:,} VNĐ"
    )
    await bot.send_message(
        chat_id=ADMIN_GROUP_ID, text=admin_msg, parse_mode="Markdown"
    )

  await callback.message.answer(
      f"✅ **GIAO DỊCH THÀNH CÔNG!**\n\n"
      f"• Bạn đã mua: **{product['name']}**\n"
      f"• Trừ ví: -{price:,} VNĐ\n"
      f"• Số dư còn lại: `{db[user_id]:,} VNĐ`\n\n"
      f"👉 Admin sẽ gửi thông tin tài khoản qua tin nhắn cho bạn ngay bây giờ.",
      parse_mode="Markdown",
  )
  await callback.answer()


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

