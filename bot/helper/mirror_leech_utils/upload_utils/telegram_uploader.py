from asyncio import sleep
from os import walk, rename, path as ospath, remove as osremove
from time import time
from bot import AS_DOC_USERS, AS_DOCUMENT, AS_MEDIA_USERS, DUMP_CHAT, EXTENSION_FILTER, LOGGER, Bot, app
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatType
from PIL import Image
from bot.helper.ext_utils.human_format import get_readable_file_size
from bot.helper.ext_utils.misc_utils import get_media_info, get_media_streams
from bot.helper.ext_utils.screenshot import take_ss

IMAGE_SUFFIXES = ("jpg", "jpx", "png", "cr2", "tif", "bmp", "jxr", "psa", "ico", "heic", "jpeg")

class TelegramUploader():
    def __init__(self, path, name, size, listener= None) -> None:
        self.client= app if app is not None else Bot
        self.__path = path
        self.__listener = listener
        self.name= name
        self.__size= size
        self.__total_files = 0
        self.__corrupted = 0
        self.__is_corrupted = False
        self.__is_cancelled = False
        self.__msgs_dict = {}
        self.__as_doc = AS_DOCUMENT
        self.__isPrivate = listener.message.chat.type == ChatType.PRIVATE
        self.__thumb = f"Thumbnails/{listener.message.chat.id}.jpg"
        self.__start_time= time()
        self.uploaded_bytes = 0
        self._last_uploaded = 0
        self.__set__user_settings()

    async def upload(self):
        await self.__msg_to_reply() 
        if ospath.isdir(self.__path):
            for dirpath, _, filenames in sorted(walk(self.__path)):
                for file in sorted(filenames):
                    if not file.lower().endswith(tuple(EXTENSION_FILTER)):
                        self.__total_files += 1   
                        f_path = ospath.join(dirpath, file)
                        f_size = ospath.getsize(f_path)
                        if f_size == 0:
                            LOGGER.error(f"{f_size} size is zero, telegram don't upload zero size files")
                            self.__corrupted += 1
                            continue
                        await self.__upload_file(f_path, file)
                        if self.__is_cancelled:
                            return
                        if (not self.__isPrivate or DUMP_CHAT is not None) and not self.__is_corrupted:
                            self.__msgs_dict[self.__sent_msg.link] = file
                        self._last_uploaded = 0
                        await sleep(1)
        if self.__total_files <= self.__corrupted:
            return await self.__listener.onUploadError('Files Corrupted. Check logs')
        size = get_readable_file_size(self.__size)
        await self.__listener.onUploadComplete(None, size, self.__msgs_dict, self.__total_files, self.__corrupted, self.name)    
    
    async def __upload_file(self, up_path, file):
        thumb_path = self.__thumb
        notMedia = False
        self.__is_corrupted = False
        cap= f"<code>{file}</code>"
        try:
            is_video, is_audio = get_media_streams(up_path)
            if not self.__as_doc:
                if is_video:
                    if not str(up_path).split(".")[-1] in ['mp4', 'mkv']:
                        new_path = str(up_path).split(".")[0] + ".mp4"
                        rename(up_path, new_path) 
                        up_path = new_path
                    duration= get_media_info(up_path)[0]
                    if thumb_path is None:
                        thumb_path = take_ss(up_path, duration)
                        if self.__is_cancelled:
                            if self.__thumb is None and thumb_path is not None and ospath.lexists(thumb_path):
                                osremove(thumb_path)
                            return
                    if thumb_path is not None:
                        with Image.open(thumb_path) as img:
                            width, height = img.size
                    else:
                        width = 480
                        height = 320
                    self.__sent_msg= await self.__sent_msg.reply_video(
                        video= up_path,
                        width= width,
                        height= height,
                        caption= cap,
                        disable_notification=True,
                        parse_mode= ParseMode.HTML,
                        thumb= thumb_path,
                        supports_streaming= True,
                        duration= duration,
                        progress= self.__upload_progress)
                elif is_audio:
                    duration, artist, title = get_media_info(up_path)
                    self.__sent_msg = self.__sent_msg.reply_audio(audio=up_path,
                        quote=True,
                        caption=cap,
                        duration=duration,
                        performer=artist,
                        title=title,
                        thumb= thumb_path,
                        disable_notification=True,
                        progress=self.__upload_progress)    
                elif file.endswith(IMAGE_SUFFIXES):
                    self.__sent_msg = await self.__sent_msg.reply_photo(
                        photo=up_path,
                        caption=cap,
                        parse_mode= ParseMode.HTML,
                        disable_notification=True,
                        progress= self.__upload_progress)
                else:
                    notMedia = True
            if self.__as_doc or notMedia:
                if is_video and thumb_path is None:
                    thumb_path = take_ss(up_path, None)
                    if self.__is_cancelled:
                        if self.__thumb is None and thumb_path is not None and ospath.lexists(thumb_path):
                            osremove(thumb_path)
                        return
                self.__sent_msg= await self.__sent_msg.reply_document(
                    document= up_path, 
                    caption= cap,
                    parse_mode= ParseMode.HTML,
                    force_document= True,
                    thumb= thumb_path,
                    progress= self.__upload_progress)
        except FloodWait as f:
            LOGGER.warning(str(f))
            sleep(f.value)
        except Exception as ex:
            LOGGER.error(f"{ex} Path: {up_path}")
            self.__corrupted += 1
            self.__is_corrupted = True
        if self.__thumb is None and thumb_path is not None and ospath.lexists(thumb_path):
            osremove(thumb_path)
        if not self.__is_cancelled :
            try:
                osremove(up_path)
            except:
                pass

    def __upload_progress(self, current, total):
        if self.__is_cancelled:
            app.stop_transmission()
            return
        chunk_size = current - self._last_uploaded
        self._last_uploaded = current
        self.uploaded_bytes += chunk_size
        
    def __set__user_settings(self):
        if self.__listener.message.chat.id in AS_DOC_USERS:
            self.__as_doc = True
        elif self.__listener.message.chat.id in AS_MEDIA_USERS:
            self.__as_doc = False
        if not ospath.lexists(self.__thumb):
            self.__thumb = None

    async def __msg_to_reply(self):
        if DUMP_CHAT is not None:
            if self.__listener.isPrivate:
                msg = self.__listener.message.text
            else:
                msg = self.__listener.message.link
            self.__sent_msg = await self.client.send_message(DUMP_CHAT, msg, disable_web_page_preview=True)
        else:
            self.__sent_msg = await self.client.get_messages(self.__listener.message.chat.id, self.__listener.uid)

    @property
    def speed(self):
        try:
            return self.uploaded_bytes / (time() - self.__start_time)
        except:
            return 0

    def cancel_download(self):
        self.__is_cancelled = True
        LOGGER.info(f"Cancelling Upload: {self.name}")
        self.__listener.onUploadError('Your upload has been stopped!')