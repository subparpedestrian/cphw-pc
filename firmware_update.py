import asyncio
import logging
import time
from enum import Enum

from bleak import BleakClient, BleakScanner

logger = logging.getLogger(__name__)

FIRMWARE_BIN = 'firmware.bin'

CPHW_SERVICE_UUID = '52756265-6e43-6167-6e69-654350485000'
CPHW_OTHER_UUID = '52756265-6e43-6167-6e69-654350485001'

AUTH_REQUEST_UUID = '52756265-6e43-6167-6e69-654350485101'
AUTH_STATUS_UUID = '52756265-6e43-6167-6e69-654350485104'
BOARD_SERIAL_UUID = '52756265-6e43-6167-6e69-654350485105'

BOOTLOADER_SERVICE_UUID = '52756265-6e43-6167-6e69-654350485200'
BOOTLOADER_RESPONSE_UUID = '52756265-6e43-6167-6e69-654350485201'
BOOTLOADER_UPLOAD_UUID = '52756265-6e43-6167-6e69-654350485202'
BOOTLOADER_FLASH_UUID = '52756265-6e43-6167-6e69-654350485203'
BOOTLOADER_VERSION_UUID = '52756265-6e43-6167-6e69-654350485204'

ERASE_TIMEOUT = 30
PROGRAM_TIMEOUT = 30
CHECKSUM_TIMEOUT = 30

class UPDATE_STATE(Enum):
    IDLE = 0
    ERASING = 1
    PROGRAMMING = 2
    CHECKSUMMING = 3

update_state = UPDATE_STATE.IDLE
operation_complete = False

async def reset_to_bootloader(client: BleakClient):
    data = 'F00101'
    await client.write_gatt_char(CPHW_OTHER_UUID, bytes.fromhex(data))

async def reset_to_app(client: BleakClient):
    await client.write_gatt_char(BOOTLOADER_FLASH_UUID, bytes.fromhex('f90101'), response=True)
    await asyncio.sleep(2.0)


async def main():
    logger.info("Searching for wheel...")

    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: ad.service_uuids and CPHW_SERVICE_UUID in ad.service_uuids
        )

    if device is None:
        logger.error("No wheels found, maybe it's off or idle.")
        return

    logger.info("Connecting to wheel...")

    async with BleakClient(device) as client:
        logger.info("Connected")

        logger.info("Reading serial number")
        serial = await client.read_gatt_char(BOARD_SERIAL_UUID)

        if serial is None:
            logger.error("Could not read serial number")
            return

        serial = serial[:14].decode('ascii')
        logger.info(f"Serial number: {serial}")

        logger.info("Opening passcodes file and searching for passcode")

        code = None
        with open('passcodes.csv') as f:
            for l in f:
                ll = l.split(',')
                if ll[0] == serial:
                    code = ll[1].strip()
                    break

        if code is None:
            logger.error('Passcode not found for given serial.')
            return

        logger.info("Code found, authenticating...")

        await client.write_gatt_char(AUTH_REQUEST_UUID, bytes.fromhex(code))

        logger.info("Checking authentication status...")
        await asyncio.sleep(1.0)

        state = await client.read_gatt_char(AUTH_STATUS_UUID)

        if state is None or state == 0xFF:
            logger.error("Authentication unsuccessful or could not read auth state")
            return

        logger.info(f"Authentication success. level: 0x{state.hex()}")

        await asyncio.sleep(0.5)
        logger.info("resetting into bootloader...")

        await reset_to_bootloader(client)
        await asyncio.sleep(2)

        logger.info('disconnecting so we can reconect...')

    logger.info('disconnected')
    logger.info('reconnecting')

    async with BleakClient(device) as client:
        global update_state
        global active_block
        global operation_complete
        update_state = UPDATE_STATE.IDLE

        async def notification_handler(_, data):
            logger.info(f"notified of: {data.hex()}")
            global update_state
            global operation_complete
            match update_state:
                case UPDATE_STATE.ERASING:
                    operation_complete = True
                case UPDATE_STATE.PROGRAMMING:
                    operation_complete = True
                case UPDATE_STATE.CHECKSUMMING:
                    operation_complete = True
                case _:
                    pass

        async def check_checksum():
            global update_state
            logger.info("checking checksum")
            update_state = UPDATE_STATE.CHECKSUMMING
            await client.write_gatt_char(BOOTLOADER_FLASH_UUID, bytes.fromhex('FB'))

        async def request_erase(data: bytearray):
            global update_state
            logger.info(f"requesting erase with data: {data.hex()}")
            update_state = UPDATE_STATE.ERASING
            await client.write_gatt_char(BOOTLOADER_FLASH_UUID, data)

        async def request_program(data: bytearray):
            global update_state
            logger.debug(f"writing program data: {data.hex()}")
            update_state = UPDATE_STATE.PROGRAMMING
            await client.write_gatt_char(BOOTLOADER_UPLOAD_UUID, data)

        async def keep_going():
            global active_block
            if active_block < len(program_blocks):
                logger.info(f'Programming block {active_block+1} of {len(program_blocks)}')
                await request_program(program_blocks[active_block])
                active_block = active_block + 1
            else:
                await check_checksum()


        logger.info("connected")
        await client.start_notify(BOOTLOADER_RESPONSE_UUID, notification_handler)

        erase_data = None
        program_blocks = []
        active_block = 0
        with open(FIRMWARE_BIN, 'rb') as f:
            d = f.read()
            erase_data = d[0:10]
            d = d[10:]
            program_blocks = [d[i*64:i*64+64] for i in range(int(len(d) / 64))]

        await request_erase(erase_data)

        timeout = time.time() + ERASE_TIMEOUT
        while (update_state is not UPDATE_STATE.IDLE):
            if (operation_complete):
                operation_complete = False
                match update_state:
                    case UPDATE_STATE.ERASING:
                        timeout = time.time() + PROGRAM_TIMEOUT
                        await keep_going()
                    case UPDATE_STATE.PROGRAMMING:
                        timeout = time.time() + PROGRAM_TIMEOUT
                        await keep_going()
                    case UPDATE_STATE.CHECKSUMMING:
                        update_state = UPDATE_STATE.IDLE
                        await reset_to_app(client)
                    case _:
                        pass

            if time.time() > timeout:
                update_state = UPDATE_STATE.IDLE
                logger.warning("Timeout!!")

            await asyncio.sleep(0.1)

        await client.stop_notify(BOOTLOADER_RESPONSE_UUID)
        logger.info("Disconnecting...")

    logger.info("Disconnected")

if __name__ == "__main__":

    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
    )

    asyncio.run(main())
