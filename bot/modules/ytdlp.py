# Source: https://github.com/anasty17/mirror-leech-telegram-bot/blob/master/bot/modules/ytdlp.py
# Adapted for asyncio framework and pyrogram library

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import regex, command
from bot import DOWNLOAD_DIR, Bot
from re import split as re_split
from bot.helper.ext_utils.bot_commands import BotCommands
from bot.helper.ext_utils.bot_utils import is_url
from bot.helper.ext_utils.filters import CustomFilters
from bot.helper.ext_utils.human_format import get_readable_file_size
from bot.helper.ext_utils.message_utils import editMessage, sendMarkup, sendMessage
from bot.helper.ext_utils.misc_utils import ButtonMaker
from bot.helper.ext_utils.rclone_utils import is_rclone_config, is_rclone_drive
from bot.helper.mirror_leech_utils.download_utils.yt_dlp_helper import YoutubeDLHelper
from bot.helper.mirror_leech_utils.listener import MirrorLeechListener

listener_dict = {}


async def _ytdl(client, message, isLeech=False):
    mssg = message.text
    user_id = message.from_user.id
    msg_id = message.id

    if await is_rclone_config(user_id, message) == False:
        return

    if not isLeech:
        if await is_rclone_drive(user_id, message) == False:
            return

    link = mssg.split()
    if len(link) > 1:
        link = link[1].strip()
    else:
        link = ""

    name = mssg.split('|', maxsplit=1)
    if len(name) > 1:
        if 'opt: ' in name[0]:
            name = ''
        else:
            name = name[1]
        if name != '':
            name = re_split('pswd:|opt:', name)[0]
            name = name.strip()
    else:
        name = ''

    opt = mssg.split(' opt: ')
    if len(opt) > 1:
        opt = opt[1]
    else:
        opt = None

    if message.from_user.username:
        tag = f"@{message.from_user.username}"
    else:
        tag = message.from_user.first_name

    reply_to = message.reply_to_message
    if reply_to is not None:
        if len(link) == 0:
            link = reply_to.text.split(maxsplit=1)[0].strip()
        if reply_to.from_user.username:
            tag = f"@{reply_to.from_user.username}"
        else:
            tag = reply_to.from_user.first_name

    if not is_url(link):
        help_msg = """
<b>Send link along with command line:</b>
<code>/cmd</code> link opt: x:y|x1:y1

<b>By replying to link:</b>
<code>/cmd</code> opt: x:y|x1:y1

<b>Options Example:</b> opt: playliststart:^10|matchtitle:S13|writesubtitles:true|live_from_start:true|postprocessor_args:{"ffmpeg": ["-threads", "4"]}|wait_for_video:(5, 100)

<b>Options Note:</b> Add `^` before integer, some values must be integer and some string.
Like playlist_items: 10 works with string, so no need to add `^` before the number but playlistend works only with integer so you must add `^` before the number like example above.
You can add tuple and dict also. Use double quotes inside dict.
        """
        return await sendMessage(help_msg, message)

    listener = MirrorLeechListener(message, tag, user_id, isLeech=isLeech)
    buttons = ButtonMaker()
    best_video = "bv*+ba/b"
    best_audio = "ba/b"
    ydl = YoutubeDLHelper(message)
    try:
        result = ydl.extractMetaData(link, name, opt, True)
    except Exception as e:
        msg = str(e).replace('<', ' ').replace('>', ' ')
        return await sendMessage(tag + " " + msg, message)
    if 'entries' in result:
        for i in ['144', '240', '360', '480', '720', '1080', '1440', '2160']:
            video_format = f"bv*[height<={i}][ext=mp4]+ba[ext=m4a]/b[height<={i}]"
            b_data = f"{i}|mp4"
            formats_dict[b_data] = video_format
            buttons.cb_buildbutton(f"{i}-mp4", f"qu {msg_id} {b_data} t")
            video_format = f"bv*[height<={i}][ext=webm]+ba/b[height<={i}]"
            b_data = f"{i}|webm"
            formats_dict[b_data] = video_format
            buttons.cb_buildbutton(f"{i}-webm", f"qu {msg_id} {b_data} t")
        buttons.cb_buildbutton("MP3", f"qu {msg_id} mp3 t")
        buttons.cb_buildbutton("Best Videos", f"qu {msg_id} {best_video} t")
        buttons.cb_buildbutton("Best Audios", f"qu {msg_id} {best_audio} t")
        buttons.cb_buildbutton("Cancel", f"qu {msg_id} cancel")
        YTBUTTONS = buttons.build_menu(3)
        listener_dict[msg_id] = [listener, user_id, link, name, YTBUTTONS, opt, formats_dict]
        await sendMarkup('Choose Playlist Videos Quality:', message, YTBUTTONS)
    else:
        formats = result.get('formats')
        formats_dict = {}
        if formats is not None:
            for frmt in formats:
                if frmt.get('tbr'):

                    format_id = frmt['format_id']

                    if frmt.get('filesize'):
                        size = frmt['filesize']
                    elif frmt.get('filesize_approx'):
                        size = frmt['filesize_approx']
                    else:
                        size = 0

                    if frmt.get('height'):
                        height = frmt['height']
                        ext = frmt['ext']
                        fps = frmt['fps'] if frmt.get('fps') else ''
                        b_name = f"{height}p{fps}-{ext}"
                        if ext == 'mp4':
                            v_format = f"bv*[format_id={format_id}]+ba[ext=m4a]/b[height={height}]"
                        else:
                            v_format = f"bv*[format_id={format_id}]+ba/b[height={height}]"
                    elif frmt.get('video_ext') == 'none' and frmt.get('acodec') != 'none':
                        b_name = f"{frmt['acodec']}-{frmt['ext']}"
                        v_format = f"ba[format_id={format_id}]"
                    else:
                        continue

                    if b_name in formats_dict:
                        formats_dict[b_name][str(frmt['tbr'])] = [size, v_format]
                    else:
                        subformat = {}
                        subformat[str(frmt['tbr'])] = [size, v_format]
                        formats_dict[b_name] = subformat

            for b_name, d_dict in formats_dict.items():
                if len(d_dict) == 1:
                    tbr, v_list = list(d_dict.items())[0]
                    buttonName = f"{b_name} ({get_readable_file_size(v_list[0])})"
                    buttons.cb_buildbutton(buttonName, f"qu {msg_id} {b_name}|{tbr}")
                else:
                    buttons.cb_buildbutton(b_name, f"qu {msg_id} dict {b_name}")
        buttons.cb_buildbutton("MP3", f"qu {msg_id} mp3")
        buttons.cb_buildbutton("Best Video", f"qu {msg_id} {best_video}")
        buttons.cb_buildbutton("Best Audio", f"qu {msg_id} {best_audio}")
        buttons.cb_buildbutton("Cancel", f"qu {msg_id} close")
        YTBUTTONS = buttons.build_menu(2)
        listener_dict[msg_id] = [listener, user_id, link, name, YTBUTTONS, opt, formats_dict]
        await sendMarkup('Choose Video Quality:', message, YTBUTTONS)

async def _qual_subbuttons(task_id, b_name, msg):
    buttons = ButtonMaker()
    task_info = listener_dict[task_id]
    formats_dict = task_info[6]
    for tbr, d_data in formats_dict[b_name].items():
        buttonName = f"{tbr}K ({get_readable_file_size(d_data[0])})"
        buttons.cb_buildbutton(buttonName, f"qu {task_id} {d_data[1]}")
    buttons.cb_buildbutton("Back", f"qu {task_id} back")
    buttons.cb_buildbutton("Cancel", f"qu {task_id} close")
    SUBBUTTONS = buttons.build_menu(2)
    await editMessage(f"Choose Bit rate for <b>{b_name}</b>:", msg, SUBBUTTONS)

async def _mp3_subbuttons(task_id, msg, playlist=False):
    buttons = ButtonMaker()
    audio_qualities = [64, 128, 320]
    for q in audio_qualities:
        if playlist:
            i = 's'
            audio_format = f"ba/b-{q} t"
        else:
            i = ''
            audio_format = f"ba/b-{q}"
        buttons.cb_buildbutton(f"{q}K-mp3", f"qu {task_id} {audio_format}")
    buttons.cb_buildbutton("Back", f"qu {task_id} back")
    buttons.cb_buildbutton("Cancel", f"qu {task_id} close")
    SUBBUTTONS = buttons.build_menu(2)
    await editMessage(f"Choose Audio{i} Bitrate:", msg, SUBBUTTONS)

async def select_format(client, callback_query):
    query = callback_query
    user_id = query.from_user.id
    data = query.data
    message = query.message
    data = data.split(" ")
    task_id = int(data[1])
    try:
        task_info = listener_dict[task_id]
    except:
        return await editMessage("This is an old task", message)
    uid = task_info[1]
    if user_id != uid and not CustomFilters._owner_query(user_id):
        return await query.answer(text="This task is not for you!", show_alert=True)
    elif data[2] == "dict":
        await query.answer()
        b_name = data[3]
        await _qual_subbuttons(task_id, b_name, message)
        return
    elif data[2] == "back":
        await query.answer()
        return await editMessage('Choose Video Quality:', message, task_info[3])
    elif data[2] == "mp3":
        await query.answer()
        if len(data) == 4:
            playlist = True
        else:
            playlist = False
        await _mp3_subbuttons(task_id, message, playlist)
        return
    elif data[2] == "close":
        await query.answer("Closed")
        await message.delete()
    else:
        await query.answer()
        listener= task_info[0]
        link = task_info[2]
        name = task_info[3]
        opt = task_info[5]
        qual = data[2]
        if len(data) == 4:
            playlist = True
            if '|' in qual:
                qual = task_info[6][qual]
        else:
            playlist = False
            if '|' in qual:
                b_name, tbr = qual.split('|')
                qual = task_info[6][b_name][tbr][1]
        ydl_hp = YoutubeDLHelper(listener)
        await ydl_hp.add_download(link, f'{DOWNLOAD_DIR}{task_id}', name, qual, playlist, opt)
    del listener_dict[task_id]

async def ytdlleech(client, message):
    await _ytdl(client, message, isLeech=True)

async def ytdlmirror(client, message):
    await _ytdl(client, message)

ytdl_handler = MessageHandler(ytdlmirror, filters= command(BotCommands.YtdlMirrorCommand))
ytdl_leech_handler = MessageHandler(ytdlleech, filters= command(BotCommands.YtdlLeechCommand))
quality_handler = CallbackQueryHandler(select_format, filters= regex("qu"))

Bot.add_handler(ytdl_handler)
Bot.add_handler(ytdl_leech_handler)
Bot.add_handler(quality_handler)
