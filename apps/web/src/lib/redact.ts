const secretPattern =
  /eyJ[\w-]+\.[\w-]+\.[\w-]+|(?:sk|pk)_(?:test|live)_[\w$]+|Bearer\s+\S+/g;

export function redact(value: string) {
  return value.replace(secretPattern, "[redacted]").slice(0, 160);
}
