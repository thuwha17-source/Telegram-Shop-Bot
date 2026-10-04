import asyncio
import json
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import web

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))

# Thông tin chuyển khoản MBBank
BANK_ID = "mbbank"
ACCOUNT_NO = "0929388991"
ACCOUNT_NAME = "NGUYEN HA ANH THU"

DATA_FILE = "data_store.json"


def load_data():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      pass
  return {"users": {}, "orders": {}}


def save_data(data):
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


db = load_data()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class DepositState(StatesGroup):
  waiting_amount = State()


class DeliverState(StatesGroup):
  waiting_product_data = State()


# 2 sản phẩm Shopee hiển thị mua trực tiếp trên Bot
PRODUCTS = {
    "zin": {"name": "Zin • 4.5", "price": 4500},
    "da": {"name": "Đá • 3.5", "price": 3500},
}


def get_main_menu(user_id: int):
  balance = db["users"].get(str(user_id), 0)
  buttons = [
      [
          InlineKeyboardButton(
              text=f"🛒 Mua hàng: {item['name']}", callback_data=f"buy_{key}"
          )
      ]
      for key, item in PRODUCTS.items()
  ]
  buttons.append(
      [InlineKeyboardButton(text="💳 Nạp tiền vào ví", callback_data="topup")]
  )
  buttons.append([
      InlineKeyboardButton(
          text="💬 Mua TikTok (Nhắn tin riêng Admin)",
          url="https://t.me/bitnadior",
      )
  ])

  text = (
      f"🌸 **BITNAdior_S_bot chào khách yêu ạ!** 🌸\n"
      f"━━━━━━━━━━━━━━━━━━\n"
      f"💰 **Số dư ví của bạn:** `{balance:,} VNĐ`\n\n"
      f"Hiện tại bên em có 6 sản phẩm, hiện bot đang hiện 2 sp shopee còn tiktok"
      f" khách ib riêng e, khách yêu quan tâm vui lòng nhấn **Mua hàng**.\n\n"
      f"📌 **Chính sách:**\n"
      f"• Bên em chỉ bảo hành đúng **1 day** cho sản phẩm shopee.\n"
      f"• Mục ac new ➔ **không bảo hành** (khuyến khích mua sim tự"
      f" tạo).\n\n"
      f"💕 *Cảm ơn khách quý nhà em đã đọc ~*"
  )
  return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def send_welcome(message: Message, state: FSMContext):
  await state.clear()
  uid = str(message.from_user.id)
  if uid not in db["users"]:
    db["users"][uid] = 0
    save_data(db)
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


# --- NẠP TIỀN VÍ ---
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
      "👉 Vui lòng nhập số tiền muốn nạp (ví dụ: `10000` hoặc `50000`):",
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
          [InlineKeyboardButton(text="🔙 Quay lại Menu", callback_data="back_home")],
      ]
  )

  caption = (
      f"💳 **LỆNH NẠP TIỀN: {code}**\n\n"
      f"• Ngân hàng: **MBBank**\n"
      f"• STK: `{ACCOUNT_NO}`\n"
      f"• Chủ TK: **{ACCOUNT_NAME}**\n"
      f"• Số tiền: **{amount:,} VNĐ**\n"
      f"• Nội dung chuyển khoản: `{code}`\n\n"
      f"👉 Sau khi chuyển khoản đúng số tiền và nội dung trên, bấm nút xác nhận bên dưới."
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
    try:
      await bot.send_message(
          chat_id=ADMIN_GROUP_ID,
          text=admin_msg,
          reply_markup=admin_kb,
          parse_mode="Markdown",
      )
    except Exception as e:
      logging.error(f"Lỗi gửi admin group: {e}")

  await callback.message.answer(
      "✅ Đã gửi thông báo cho admin! Vui lòng chờ admin duyệt số dư nhé."
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("approve_"))
async def approve_topup(callback: CallbackQuery):
  _, uid_str, amt_str = callback.data.split("_")
  amount = int(amt_str)

  current_bal = db["users"].get(uid_str, 0)
  db["users"][uid_str] = current_bal + amount
  save_data(db)

  await callback.message.edit_text(
      f"{callback.message.text}\n\n🟢 **ĐÃ DUYỆT BỞI:** @{callback.from_user.username or callback.from_user.first_name}"
  )

  try:
    await bot.send_message(
        chat_id=int(uid_str),
        text=(
            f"🎉 **NẠP TIỀN THÀNH CÔNG!**\n\n"
            f"• Số tiền cộng: `+{amount:,} VNĐ`\n"
            f"• Số dư mới: `{db['users'][uid_str]:,} VNĐ`\n\n"
            f"Gõ /start để tiếp tục mua hàng!"
        ),
        parse_mode="Markdown",
    )
  except Exception:
    pass

  await callback.answer("Đã duyệt thành công!")


# --- MUA HÀNG & GIAO THỦ CÔNG QUA NHÓM ADMIN ---
@dp.callback_query(F.data.startswith("buy_"))
async def handle_buy(callback: CallbackQuery):
  product_key = callback.data.split("_", 1)[1]
  product = PRODUCTS.get(product_key)
  if not product:
    return

  user_id = str(callback.from_user.id)
  current_bal = db["users"].get(user_id, 0)
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

  # Trừ tiền ví
  db["users"][user_id] = current_bal - price
  order_id = f"DH{int(asyncio.get_event_loop().time() * 10) % 1000000}"
  db["orders"][order_id] = {
      "user_id": user_id,
      "product_name": product["name"],
      "price": price,
  }
  save_data(db)

  user = callback.from_user
  username = f"@{user.username}" if user.username else f"ID: {user.id}"

  deliver_kb = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="📤 Giao hàng cho khách", callback_data=f"sendorder_{order_id}"
          )
      ]]
  )

  if ADMIN_GROUP_ID != 0:
    admin_msg = (
        f"🛍 **ĐƠN HÀNG MỚI! Mã: `#{order_id}`**\n\n"
        f"• Khách hàng: {username}\n"
        f"• Mặt hàng: **{product['name']}**\n"
        f"• Đã trừ ví: -{price:,} VNĐ\n"
        f"• Số dư ví khách: `{db['users'][user_id]:,} VNĐ`\n\n"
        f"👉 Lấy số từ kho ngoài rồi bấm nút bên dưới để gửi thẳng cho khách:"
    )
    try:
      await bot.send_message(
          chat_id=ADMIN_GROUP_ID,
          text=admin_msg,
          reply_markup=deliver_kb,
          parse_mode="Markdown",
      )
    except Exception as e:
      logging.error(f"Lỗi gửi đơn vào nhóm: {e}")

  await callback.message.answer(
      f"✅ **ĐẶT HÀNG THÀNH CÔNG!**\n\n"
      f"• Mã đơn: `#{order_id}`\n"
      f"• Sản phẩm: **{product['name']}**\n"
      f"• Trừ ví: -{price:,} VNĐ\n"
      f"• Số dư còn lại: `{db['users'][user_id]:,} VNĐ`\n\n"
      f"⏳ Đơn hàng đang được chuẩn bị và sẽ gửi ngay vào tin nhắn này cho bạn (1-3 phút).",
      parse_mode="Markdown",
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("sendorder_"))
async def prompt_deliver(callback: CallbackQuery, state: FSMContext):
  order_id = callback.data.split("_", 1)[1]
  order = db["orders"].get(order_id)

  if not order:
    await callback.answer("Đơn hàng không tồn tại hoặc đã xử lý xong!")
    return

  await state.update_data(
      delivering_order_id=order_id,
      message_id=callback.message.message_id,
      original_text=callback.message.text,
  )
  await state.set_state(DeliverState.waiting_product_data)

  await callback.message.reply(
      f"✍️ **NHẬP SỐ / ACC CHO ĐƠN `#{order_id}`:**\n\n"
      f"Dán số điện thoại hoặc thông tin tài khoản ngay vào nhóm này, bot sẽ tự động gửi thẳng cho khách."
  )
  await callback.answer()


@dp.message(DeliverState.waiting_product_data)
async def deliver_product_to_user(message: Message, state: FSMContext):
  data = await state.get_data()
  order_id = data.get("delivering_order_id")
  original_text = data.get("original_text")
  msg_id = data.get("message_id")

  order = db["orders"].get(order_id)
  if not order:
    await message.reply("Đơn hàng không tìm thấy!")
    await state.clear()
    return

  product_info = message.text.strip()
  target_user_id = int(order["user_id"])

  # Gửi hàng trực tiếp vào tin nhắn cho khách
  try:
    await bot.send_message(
        chat_id=target_user_id,
        text=(
            f"🎉 **ĐƠN HÀNG CỦA BẠN ĐÃ ĐƯỢC GIAO!**\n\n"
            f"• Mã đơn: `#{order_id}`\n"
            f"• Sản phẩm: **{order['product_name']}**\n\n"
            f"📦 **THÔNG TIN SẢN PHẨM:**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"`{product_info}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 Chạm vào dòng trên để sao chép."
        ),
        parse_mode="Markdown",
    )
    delivery_success = True
  except Exception as e:
    logging.error(f"Lỗi gửi hàng cho khách: {e}")
    delivery_success = False

  if delivery_success:
    await message.reply(f"✅ Đã giao thành công cho đơn `#{order_id}`!")
    try:
      admin_name = message.from_user.username or message.from_user.first_name
      await bot.edit_message_text(
          chat_id=message.chat.id,
          message_id=msg_id,
          text=f"{original_text}\n\n🟢 **ĐÃ GIAO BỞI:** @{admin_name}\n📦 **Đã gửi:** `{product_info}`",
      )
    except Exception:
      pass
    db["orders"].pop(order_id, None)
    save_data(db)
  else:
    await message.reply(
        "❌ Không thể gửi tin nhắn cho khách (có thể khách đã chặn bot)."
    )

  await state.clear()


# Web server nền đáp ứng kiểm tra của Render Web Service
async def handle_ping(request):
  return web.Response(text="Bot is running!")


async def run_web():
  app = web.Application()
  app.router.add_get("/", handle_ping)
  runner = web.AppRunner(app)
  await runner.setup()
  port = int(os.getenv("PORT", 8080))
  site = web.TCPSite(runner, "0.0.0.0", port)
  await site.start()


async def main():
  print("Bot đang hoạt động...")
  await run_web()
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
