/** Saves a fetched Blob (an xlsx/pdf export) to the visitor's downloads, under a real
 * filename -- the same trick every "Download" button on the academics screens uses. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
