export function reportCalmDiagnostic(message: string): void {
  process.stderr.write(`${message}\n`);
}
