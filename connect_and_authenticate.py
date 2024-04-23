import asyncio
import logging

from bleak import BleakClient, BleakScanner

logger = logging.getLogger(__name__)

CPHW_SERVICE_UUID = '52756265-6e43-6167-6e69-654350485000'
AUTH_REQUEST_UUID = '52756265-6e43-6167-6e69-654350485101'
AUTH_STATUS_UUID = '52756265-6e43-6167-6e69-654350485104'
BOARD_SERIAL_UUID = '52756265-6e43-6167-6e69-654350485105'


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

        logger.info("Disconnecting...")

    logger.info("Disconnected")

if __name__ == "__main__":

    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
    )

    asyncio.run(main())
