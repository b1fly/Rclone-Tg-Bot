# Source: https://github.com/anasty17/mirror-leech-telegram-bot/blob/master/bot/modules/rss.py
# Adapted for asyncio framework and pyrogram library

from asyncio import Lock
from feedparser import parse as feedparse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from asyncio import sleep
from copy import deepcopy
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.filters import regex, command
from bot import DB_URI, LOGGER, RSS_CHAT_ID, RSS_COMMAND, RSS_DELAY, Bot, rss_dict
from bot.helper.ext_utils.bot_commands import BotCommands
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.ext_utils.filters import CustomFilters
from bot.helper.ext_utils.message_utils import editMessage, sendMarkup, sendMessage, sendRss
from bot.helper.ext_utils.misc_utils import ButtonMaker

rss_dict_lock = Lock()
rss_job_enabled = True



async def rss_list(client, message):
    if len(rss_dict) > 0:
        list_feed = "<b>Your subscriptions: </b>\n\n"
        for title, data in rss_dict.items():
            list_feed += f"<b>Title:</b> <code>{title}</code>\n<b>Feed Url: </b><code>{data['link']}</code>\n\n"
        await sendMessage(list_feed, message)
    else:
        await sendMessage("No subscriptions.", message)

async def rss_get(client, message):
    try:
        msg= message.text.split(maxsplit=1)
        if len(msg) > 1:
            args= msg[1].split()
            title = args[0]
            count = int(args[1])
            data = rss_dict.get(title)
            if data is not None and count > 0:
                try:
                    msg = await sendMessage(f"Getting the last <b>{count}</b> item(s) from {title}", message)
                    rss_d = feedparse(data['link'])
                    item_info = ""
                    for item_num in range(count):
                        try:
                            link = rss_d.entries[item_num]['links'][1]['href']
                        except IndexError:
                            link = rss_d.entries[item_num]['link']
                        item_info += f"<b>Name: </b><code>{rss_d.entries[item_num]['title'].replace('>', '').replace('<', '')}</code>\n"
                        item_info += f"<b>Link: </b><code>{link}</code>\n\n"
                    await editMessage(item_info, msg)
                except IndexError as e:
                    LOGGER.error(str(e))
                    await editMessage("Parse depth exceeded. Try again with a lower value.", msg)
                except Exception as e:
                    LOGGER.error(str(e))
                    await editMessage(str(e), msg)
            else:
                await sendMessage("Send a valid title/value.", message)
        else:
            await sendMessage("Send a title/value.", message)
    except (IndexError, ValueError):
        await sendMessage(f"Use this format to fetch:\n/{BotCommands.RssGetCommand[0]} Title value", message)

async def rss_sub(client, message):
    try:
        args = message.text.split(maxsplit=3)
        title = args[1].strip()
        feed_link = args[2].strip()
        f_lists = []

        if len(args) == 4:
            filters = args[3].lstrip().lower()
            if filters.startswith('f: '):
                filters = filters.split('f: ', 1)[1]
                filters_list = filters.split('|')
                for x in filters_list:
                   y = x.split(' or ')
                   f_lists.append(y)
            else:
                filters = None
        else:
            filters = None

        exists = rss_dict.get(title)
        if exists:
            return await sendMessage("This title already subscribed! Choose another title!", message)
        try:
            rss_d = feedparse(feed_link)
            sub_msg = "<b>Subscribed!</b>"
            sub_msg += f"\n\n<b>Title: </b><code>{title}</code>\n<b>Feed Url: </b>{feed_link}"
            sub_msg += f"\n\n<b>latest record for </b>{rss_d.feed.title}:"
            sub_msg += f"\n\n<b>Name: </b><code>{rss_d.entries[0]['title'].replace('>', '').replace('<', '')}</code>"
            try:
                link = rss_d.entries[0]['links'][1]['href']
            except IndexError:
                link = rss_d.entries[0]['link']
            sub_msg += f"\n\n<b>Link: </b><code>{link}</code>"
            sub_msg += f"\n\n<b>Filters: </b><code>{filters}</code>"
            last_link = rss_d.entries[0]['link']
            last_title = rss_d.entries[0]['title']
            async with rss_dict_lock:
                if len(rss_dict) == 0:
                    rss_job.resume()
                    globals()['rss_job_enabled'] = True
                rss_dict[title] = {'link': feed_link, 'last_feed': last_link, 'last_title': last_title, 'filters': f_lists}
            DbManger().rss_add(title, feed_link, last_link, last_title, filters)
            await sendMessage(sub_msg, message)
            LOGGER.info(f"Rss Feed Added: {title} - {feed_link} - {filters}")
        except (IndexError, AttributeError) as e:
            msg = "The link doesn't seem to be a RSS feed or it's region-blocked!"
            await sendMessage(msg + '\nError: ' + str(e), message)
        except Exception as e:
            await sendMessage(str(e), message)
    except IndexError:
        msg = f"Use this format to add feed url:\n/{BotCommands.RssSubCommand[0]} Title https://www.rss-url.com"
        msg += " f: 1080 or 720 or 144p|mkv or mp4|hevc (optional)\n\nThis filter will parse links that it's titles"
        msg += " contains `(1080 or 720 or 144p) and (mkv or mp4) and hevc` words. You can add whatever you want.\n\n"
        msg += "Another example: f:  1080  or 720p|.web. or .webrip.|hvec or x264. This will parse titles that contains"
        msg += " ( 1080  or 720p) and (.web. or .webrip.) and (hvec or x264). I have added space before and after 1080"
        msg += " to avoid wrong matching. If this `10805695` number in title it will match 1080 if added 1080 without"
        msg += " spaces after it."
        msg += "\n\nFilters Notes:\n\n1. | means and.\n\n2. Add `or` between similar keys, you can add it"
        msg += " between qualities or between extensions, so don't add filter like this f: 1080|mp4 or 720|web"
        msg += " because this will parse 1080 and (mp4 or 720) and web ... not (1080 and mp4) or (720 and web)."
        msg += "\n\n3. You can add `or` and `|` as much as you want."
        msg += "\n\n4. Take look on title if it has static special character after or before the qualities or extensions"
        msg += " or whatever and use them in filter to avoid wrong match"
        await sendMessage(msg, message)

async def rss_unsub(client, message):
    try:
        msg= message.text.split(maxsplit=1)
        args= msg[1].split()
        title = args[0]
        exists = rss_dict.get(title)
        if not exists:
            msg = "Rss link not exists! Nothing removed!"
            await sendMessage(msg, message)
        else:
            DbManger().rss_delete(title)
            async with rss_dict_lock:
                del rss_dict[title]
            await sendMessage(f"Rss link with Title: <code>{title}</code> has been removed!", message)
            LOGGER.info(f"Rss link with Title: {title} has been removed!")
    except IndexError:
        await sendMessage(f"Use this format to remove feed url:\n/{BotCommands.RssUnSubCommand} Title", message)

async def rss_settings(client, message):
    buttons = ButtonMaker()
    buttons.cb_buildbutton("Unsubscribe All", "rss unsuball")
    if rss_job_enabled:
        buttons.cb_buildbutton("Pause", "rss pause")
    else:
        buttons.cb_buildbutton("Start", "rss start")
    buttons.cb_buildbutton("Close", "rss close")
    button = buttons.build_menu(1)
    await sendMarkup('Rss Settings', message, button)

async def rss_set_update(client, callback_query):
    query = callback_query
    user_id = query.from_user.id
    msg = query.message
    data = query.data
    data = data.split()
    if not CustomFilters._owner_query(user_id):
        await query.answer(text="You don't have permission to use these buttons!", show_alert=True)
    elif data[1] == 'unsuball':
        await query.answer()
        if len(rss_dict) > 0:
            DbManger().trunc_table('rss')
            async with rss_dict_lock:
                rss_dict.clear()
            rss_job.pause()
            globals()['rss_job_enabled'] = False
            await editMessage("All Rss Subscriptions have been removed.", msg)
            LOGGER.info("All Rss Subscriptions have been removed.")
        else:
            await editMessage("No subscriptions to remove!", msg)
    elif data[1] == 'pause':
        await query.answer()
        rss_job.pause()
        globals()['rss_job_enabled'] = False
        await editMessage("Rss Paused", msg)
        LOGGER.info("Rss Paused")
    elif data[1] == 'start':
        await query.answer()
        rss_job.resume()
        globals()['rss_job_enabled'] = False
        await editMessage("Rss Started", msg)
        LOGGER.info("Rss Started")
    else:
        await query.answer()
        await query.message.delete()
        await query.message.reply_to_message.delete()

async def rss_monitor():
    async with rss_dict_lock:
        if len(rss_dict) == 0:
            rss_job.pause()
            globals()['rss_job_enabled'] = False
            return
        rss_saver = deepcopy(rss_dict)
    for title, data in rss_saver.items():
        try:
            rss_d = feedparse(data['link'])
            last_link = rss_d.entries[0]['link']
            last_title = rss_d.entries[0]['title']
            if data['last_feed'] == last_link or data['last_title'] == last_title:
                continue
            feed_count = 0
            while True:
                try:
                    if data['last_feed'] == rss_d.entries[feed_count]['link'] or \
                       data['last_title'] == rss_d.entries[feed_count]['title']:
                       break
                except IndexError:
                    LOGGER.warning(f"Reached Max index no. {feed_count} for this feed: {title}. Maybe you need to use less RSS_DELAY to not miss some torrents")
                    break
                parse = True
                for list in data['filters']:
                    if all(x not in str(rss_d.entries[feed_count]['title']).lower() for x in list):
                        parse = False
                        feed_count += 1
                        break
                if not parse:
                    continue
                try:
                    url = rss_d.entries[feed_count]['links'][1]['href']
                except IndexError:
                    url = rss_d.entries[feed_count]['link']
                if RSS_COMMAND is not None:
                    feed_msg = f"{RSS_COMMAND} {url}"
                else:
                    feed_msg = f"<b>Name: </b><code>{rss_d.entries[feed_count]['title'].replace('>', '').replace('<', '')}</code>\n\n"
                    feed_msg += f"<b>Link: </b><code>{url}</code>"
                await sendRss(feed_msg)
                feed_count += 1
                await sleep(5)
            async with rss_dict_lock:
                rss_dict[title].update({'last_feed': last_link, 'last_title': last_title})
            DbManger().rss_update(title, str(last_link), str(last_title))
            LOGGER.info(f"Feed Name: {title}")
            LOGGER.info(f"Last item: {last_link}")
        except Exception as e:
            LOGGER.error(f"{e} Feed Name: {title} - Feed Link: {data['link']}")
            continue

if DB_URI is not None and RSS_CHAT_ID is not None:
    rss_list_handler = MessageHandler(rss_list, filters= command(BotCommands.RssListCommand))
    rss_get_handler = MessageHandler(rss_get, filters= command(BotCommands.RssGetCommand))
    rss_sub_handler = MessageHandler(rss_sub, filters= command(BotCommands.RssSubCommand))
    rss_unsub_handler = MessageHandler(rss_unsub, filters= command(BotCommands.RssUnSubCommand))
    rss_settings_handler = MessageHandler(rss_settings, filters= command(BotCommands.RssSettingsCommand))
    rss_buttons_handler = CallbackQueryHandler(rss_set_update, filters= regex("rss"))

    Bot.add_handler(rss_list_handler)
    Bot.add_handler(rss_get_handler)
    Bot.add_handler(rss_sub_handler)
    Bot.add_handler(rss_unsub_handler)
    Bot.add_handler(rss_settings_handler)
    Bot.add_handler(rss_buttons_handler)

    scheduler = AsyncIOScheduler()
    rss_job = scheduler.add_job(rss_monitor, 'interval', id= "RSS", seconds=RSS_DELAY)
    scheduler.start()
