/** Decode GenLayer's binary calldata. The node's `readable` rendering is not JSON. */
export function decodeCalldata(bytes) {
  let offset = 0;
  const text = new TextDecoder();
  function readVarint() {
    let value = 0n;
    let shift = 0n;
    let byte;
    do {
      if (offset >= bytes.length) throw new Error("truncated calldata");
      byte = bytes[offset++];
      value |= BigInt(byte & 0x7f) << shift;
      shift += 7n;
    } while (byte & 0x80);
    return value;
  }
  function take(length) {
    if (offset + length > bytes.length) throw new Error("truncated calldata");
    const slice = bytes.slice(offset, offset + length);
    offset += length;
    return slice;
  }
  function readValue() {
    const tag = readVarint();
    const kind = Number(tag & 7n);
    const length = Number(tag >> 3n);
    if (kind === 4) return text.decode(take(length));
    if (kind === 5) return Array.from({ length }, readValue);
    if (kind === 6) {
      const value = {};
      for (let i = 0; i < length; i += 1) {
        const key = text.decode(take(Number(readVarint())));
        value[key] = readValue();
      }
      return value;
    }
    if (kind === 1) return BigInt(length);
    if (kind === 2) return -1n - BigInt(length);
    if (kind === 0 && length === 0) return null;
    if (kind === 0 && length === 1) return false;
    if (kind === 0 && length === 2) return true;
    throw new Error(`unsupported GenLayer calldata tag ${tag}`);
  }
  const value = readValue();
  if (offset !== bytes.length) throw new Error("trailing calldata bytes");
  return value;
}

/** `{method, args}` with integers as JS numbers, or null when it cannot be decoded. */
export function decodeCall(base64) {
  try {
    const decoded = decodeCalldata(Uint8Array.from(Buffer.from(base64, "base64")));
    const plain = (value) =>
      typeof value === "bigint" ? Number(value)
        : Array.isArray(value) ? value.map(plain) : value;
    if (!decoded || typeof decoded.method !== "string" || !Array.isArray(decoded.args)) return null;
    return { method: decoded.method, args: decoded.args.map(plain) };
  } catch {
    return null;
  }
}
