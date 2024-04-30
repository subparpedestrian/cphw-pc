def swap_every_other_byte(byte_array):
    # Loop through the bytearray two bytes at a time
    for i in range(0, len(byte_array) - 1, 2):
        # Swap bytes
        byte_array[i], byte_array[i+1] = byte_array[i+1], byte_array[i]
    return byte_array

def crc16(data: bytearray) -> int:
    crc = 0
    out = 0
    bit_flag = 0
    this_byte = 0
    bits_read = 0
    bytes_read = 0
    index = 0

    data = swap_every_other_byte(data.copy())
    byte_len = len(data)

    while byte_len > 0:
        bit_flag = out >> 15
        out <<= 1
        out &= 0xFFFF

        this_byte = data[index]

        # Get the next bit from this_byte
        out |= (this_byte >> bits_read) & 1

        bits_read += 1
        if bits_read > 7:
            bits_read = 0
            index += 1
            byte_len -= 1

        # Apply the CRC polynomial if the shifted-out bit is 1
        if bit_flag:
            out ^= 0x8005

    # Push out the last 16 bits
    for _ in range(16):
        bit_flag = out >> 15
        out <<= 1
        out &= 0xFFFF
        if bit_flag:
            out ^= 0x8005

    # Reverse the bits in the CRC
    for i in range(16):
        if out & (1 << i):
            crc |= (1 << (15 - i))

    return (crc & 0xFF, crc>>8)
