declare module 'pdfjs-dist/legacy/build/pdf.mjs' {
  export const GlobalWorkerOptions: { workerSrc: string };
  export interface PdfTextItem {
    str: string;
    hasEOL?: boolean;
  }
  export interface PdfTextContent {
    items: Array<PdfTextItem | { type?: string }>;
  }
  export interface PdfPage {
    getTextContent(): Promise<PdfTextContent>;
  }
  export interface PdfDocument {
    numPages: number;
    getPage(pageNumber: number): Promise<PdfPage>;
    destroy(): Promise<void>;
  }
  export interface PdfLoadingTask {
    promise: Promise<PdfDocument>;
  }
  export function getDocument(source: Record<string, unknown>): PdfLoadingTask;
}
