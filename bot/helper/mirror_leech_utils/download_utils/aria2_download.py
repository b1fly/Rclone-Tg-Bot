# Source: https://github.com/anasty17/mirror-leech-telegram-bot/
# Adapted for asyncio framework and pyrogram library

import asyncio
from time import sleep
from bot import LOGGER, status_dict_lock, status_dict, aria2
from bot.helper.ext_utils.bot_utils import is_magnet, new_thread
from bot.helper.ext_utils.message_utils import sendMessage, sendStatusMessage
from bot.helper.ext_utils.misc_utils import getDownloadByGid
from bot.helper.mirror_leech_utils.status_utils.aria_status import AriaDownloadStatus



@new_thread
def __onDownloadStarted(api, gid):
    download = api.get_download(gid)
    if download.is_metadata:
        LOGGER.info(f'onDownloadStarted: {gid} METADATA')
        sleep(1)
    else:
        LOGGER.info(f'onDownloadStarted: {download.name} - Gid: {gid}')

@new_thread
def __onDownloadComplete(api, gid):
    try:
        download = api.get_download(gid)
    except:
        return
    LOGGER.info(f"onDownloadComplete: {download.name} - Gid: {gid}")
    if dl := getDownloadByGid(gid):
        asyncio.run(dl.listener().onDownloadComplete())
        api.remove([download], force=True, files=True)

@new_thread
def __onBtDownloadComplete(api, gid):
    sleep(1)
    download = api.get_download(gid)
    LOGGER.info(f"onBtDownloadComplete: {download.name} - Gid: {gid}")
    if dl := getDownloadByGid(gid):
        listener = dl.listener()
        api.client.force_pause(gid)
        asyncio.run(listener.onDownloadComplete())
        api.remove([download], force=True, files=True)

@new_thread
def __onDownloadStopped(api, gid):
    sleep(6)
    if dl := getDownloadByGid(gid):
        asyncio.run(dl.listener().onDownloadError('Dead torrent!'))
        
@new_thread
def __onDownloadError(api, gid):
    LOGGER.info(f"onDownloadError: {gid}")
    error = "None"
    try:
        download = api.get_download(gid)
        error = download.error_message
        LOGGER.info(f"Download Error: {error}")
    except:
        pass
    if dl := getDownloadByGid(gid):
        asyncio.run(dl.listener().onDownloadError(error))

def start_listener():
    aria2.listen_to_notifications(threaded=True,
                                  on_download_start=__onDownloadStarted,
                                  on_download_error=__onDownloadError,
                                  on_download_stop=__onDownloadStopped,
                                  on_download_complete=__onDownloadComplete,
                                  on_bt_download_complete=__onBtDownloadComplete,
                                  timeout=60)

async def add_aria2c_download(link: str, path, listener, filename):
    args = {'dir': path, 'max-upload-limit': '1K'}
    if filename:
        args['out'] = filename
    if is_magnet(link):
        download = await asyncio.get_running_loop().run_in_executor(None, aria2.add_magnet, link, args)  
    else:
        download = await asyncio.get_running_loop().run_in_executor(None, aria2.add_uris, [link], args)
    if download.error_message:
        error = str(download.error_message).replace('<', ' ').replace('>', ' ')
        LOGGER.info(f"Download Error: {error}")
        return await sendMessage(error, listener.message)
    async with status_dict_lock:
        status_dict[listener.uid] = AriaDownloadStatus(download.gid, listener)
        LOGGER.info(f"Aria2Download started: {download.gid}")
    await sendStatusMessage(listener.message)


start_listener()
