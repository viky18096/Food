
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from datetime import datetime, time
import pytz
import asyncio 
import firebase_admin

from firebase_admin import credentials, db

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token (replace with your actual token)
TOKEN = "7402715366:AAFtwRVhutqOtsSgmnonkgD3kt4lobIvfwU"

# Initialize Firebase
cred = credentials.Certificate(r"C:\Users\vikas\Downloads\foodbot-c685c-firebase-adminsdk-rcyip-efd57534bc.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': "https://foodbot-c685c-default-rtdb.asia-southeast1.firebasedatabase.app"
})

# Database reference
ref = db.reference('/')

# Time zone (adjust as needed)
IST = pytz.timezone('Asia/Kolkata')

# Define conversation states
CHOOSING, ITEM_NAME, ITEM_PRICE, ITEM_QUANTITY, ITEM_PHOTO_OPTION, ITEM_PHOTO = range(6)


# Check if current time is between 5 PM and 6 PM
def is_order_time():
    now = datetime.now(IST).time()
    return time(17, 0) <= now <= time(21, 0)

# Firebase database operations
def add_menu_item(cook_id, item_name, price, quantity, photo_url=None):
    menu_ref = ref.child('menu_items')
    new_item = menu_ref.push()
    item_data = {
        'cook_id': cook_id,
        'item_name': item_name,
        'price': price,
        'quantity': quantity
    }
    if photo_url:
        item_data['photo_url'] = photo_url
    new_item.set(item_data)    

def get_menus():
    return ref.child('menu_items').get()

def place_order(user_id, cook_id, items):
    order_ref = ref.child('orders')
    new_order = order_ref.push()
    total_price = sum(item['price'] * item['quantity'] for item in items)
    
    order_data = {
        'user_id': user_id,
        'cook_id': cook_id,
        'total_price': total_price,
        'status': 'placed',
        'order_time': datetime.now(IST).isoformat(),
        'items': items
    }
    
    new_order.set(order_data)
    
    # Update menu item quantities
    menu_ref = ref.child('menu_items')
    for item in items:
        item_ref = menu_ref.child(item['id'])
        current_quantity = item_ref.child('quantity').get()
        item_ref.update({'quantity': current_quantity - item['quantity']})
    
    return new_order.key

async def start(update: Update, context):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("Browse Menus", callback_data='browse_menus')],
        [InlineKeyboardButton("Place Order", callback_data='place_order')],
        [InlineKeyboardButton("My Orders", callback_data='my_orders')],
        [InlineKeyboardButton("Cook Menu", callback_data='cook_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Welcome, {user.first_name}! I'm your food ordering assistant. What would you like to do?",
        reply_markup=reply_markup
    )
    return CHOOSING

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == 'browse_menus':
        await browse_menus(update, context)
    elif query.data == 'place_order':
        await place_order_command(update, context)
    elif query.data == 'my_orders':
        await my_orders(update, context)
    elif query.data == 'cook_menu':
        return await cook_menu(update, context)
    return CHOOSING

async def cook_menu(update: Update, context):
    if not is_order_time():
        await update.callback_query.message.reply_text("You can only post menus between 5 PM and 9 PM.")
        return CHOOSING

    await update.callback_query.message.reply_text("Let's add a new menu item. What's the name of the dish?")
    return ITEM_NAME

async def get_item_name(update: Update, context):
    context.user_data['new_item'] = {'name': update.message.text}
    await update.message.reply_text(f"Great! '{update.message.text}' sounds delicious. Now, what's the price?")
    return ITEM_PRICE

async def browse_menus(update: Update, context):
    menus = get_menus()
    if menus:
        for item_id, item in menus.items():
            menu_text = f"{item['item_name']} - ₹{item['price']} (Available: {item['quantity']})"
            
            keyboard = [
                [InlineKeyboardButton("Order", callback_data=f'order_{item_id}')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.message.reply_text(menu_text, reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text("No menus available.")
    return CHOOSING

async def handle_order_button(update: Update, context):
    query = update.callback_query
    await query.answer()

    item_id = query.data.split('_')[1]
    menu_item = ref.child('menu_items').child(item_id).get()

    if menu_item and menu_item['quantity'] > 0:
        # Here you would typically add the item to the user's cart
        # For this example, we'll just confirm the order
        await query.message.reply_text(f"You've ordered 1 {menu_item['item_name']}. Total: ₹{menu_item['price']}")
        
        # Decrease the quantity of the item
        new_quantity = menu_item['quantity'] - 1
        ref.child('menu_items').child(item_id).update({'quantity': new_quantity})
    else:
        await query.message.reply_text("Sorry, this item is no longer available.")

    return CHOOSING

async def get_item_price(update: Update, context):
    try:
        price = float(update.message.text)
        context.user_data['new_item']['price'] = price
        await update.message.reply_text(f"Price set to ₹{price}. How many servings are available?")
        return ITEM_QUANTITY
    except ValueError:
        await update.message.reply_text("Please enter a valid number for the price.")
        return ITEM_PRICE

async def get_item_quantity(update: Update, context):
    try:
        quantity = int(update.message.text)
        context.user_data['new_item']['quantity'] = quantity
        keyboard = [
            [InlineKeyboardButton("Yes", callback_data='add_photo')],
            [InlineKeyboardButton("No", callback_data='skip_photo')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Would you like to add a photo of the dish?", reply_markup=reply_markup)
        return ITEM_PHOTO_OPTION
    except ValueError:
        await update.message.reply_text("Please enter a valid number for the quantity.")
        return ITEM_QUANTITY

async def photo_option_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'add_photo':
        await query.message.reply_text("Great! Please send a photo of the dish.")
        return ITEM_PHOTO
    elif query.data == 'skip_photo':
        return await finalize_menu_item(update, context)

async def get_item_photo(update: Update, context):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_url = file.file_path
    context.user_data['new_item']['photo_url'] = photo_url
    return await finalize_menu_item(update, context)

async def finalize_menu_item(update: Update, context):
    new_item = context.user_data['new_item']
    user = update.effective_user if isinstance(update, Update) else update.callback_query.from_user
    

    add_menu_item(
        user.id,
        new_item['name'],
        new_item['price'],
        new_item['quantity'],
        new_item.get('photo_url')
    )
    
    message = await (update.message.reply_text if isinstance(update, Update) else update.callback_query.message.reply_text)
    await message(f"Great! Your menu item '{new_item['name']}' has been added successfully!")
    
    keyboard = [
        [InlineKeyboardButton("Add Another Item", callback_data='add_another_item')],
        [InlineKeyboardButton("Finish", callback_data='finish_adding_items')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message("Would you like to add another item or finish?", reply_markup=reply_markup)
    
    return CHOOSING


async def add_another_item(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Let's add another item.")
    return ITEM_NAME


async def finish_adding_items(update: Update, context):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Thank you for adding the menu items! Your menu is now updated.")
    return ConversationHandler.END


def main():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [
                CallbackQueryHandler(button_handler),
                CallbackQueryHandler(add_another_item, pattern='^add_another_item$'),
                CallbackQueryHandler(finish_adding_items, pattern='^finish_adding_items$'),
                CallbackQueryHandler(handle_order_button, pattern='^order_'),
            ],
            ITEM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_item_name)],
            ITEM_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_item_price)],
            ITEM_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_item_quantity)],
            ITEM_PHOTO_OPTION: [CallbackQueryHandler(photo_option_handler)],
            ITEM_PHOTO: [MessageHandler(filters.PHOTO, get_item_photo)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    application.add_handler(conv_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
