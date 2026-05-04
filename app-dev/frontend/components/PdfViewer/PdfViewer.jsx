// components/PdfViewer.jsx
"use client";

import { useState, useEffect, useRef } from "react";
import dynamic from "next/dynamic";

// Динамически импортируем PDF.js только на клиенте
const Pdfjs = dynamic(() => import("pdfjs-dist"), { ssr: false });

export default function PdfViewer({ pdfUrl, width = "100%", height = "100%" }) {
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [scale, setScale] = useState(1.0);
  const [pdfjsLoaded, setPdfjsLoaded] = useState(false);
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    // Настраиваем worker для PDF.js
    if (typeof window !== "undefined") {
      import("pdfjs-dist/build/pdf.worker.entry").then((worker) => {
        // @ts-ignore
        Pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        setPdfjsLoaded(true);
      });
    }
  }, []);

  useEffect(() => {
    if (!pdfUrl || !pdfjsLoaded) return;

    const loadPdf = async () => {
      try {
        setLoading(true);
        setError(null);
        setPageNumber(1);
        setNumPages(null);

        console.log("📄 Loading PDF:", pdfUrl);

        // Загружаем PDF
        const loadingTask = Pdfjs.getDocument(pdfUrl);
        const pdf = await loadingTask.promise;

        console.log("📄 PDF loaded:", pdf.numPages, "pages");

        setNumPages(pdf.numPages);

        // Рендерим первую страницу
        await renderPage(pdf, 1);

        setLoading(false);
      } catch (err) {
        console.error("❌ PDF Load Error:", err);
        setError(err.message || "Не удалось загрузить PDF");
        setLoading(false);
      }
    };

    const renderPage = async (pdf, pageNum) => {
      try {
        const page = await pdf.getPage(pageNum);
        const viewport = page.getViewport({ scale });

        const canvas = canvasRef.current;
        if (!canvas) return;

        const context = canvas.getContext("2d");
        if (!context) return;

        canvas.height = viewport.height;
        canvas.width = viewport.width;

        const renderContext = {
          canvasContext: context,
          viewport: viewport,
        };

        await page.render(renderContext).promise;
      } catch (err) {
        console.error("Error rendering page:", err);
      }
    };

    loadPdf();

    return () => {
      // Cleanup
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };
  }, [pdfUrl, pdfjsLoaded, scale]);

  const onPrevPage = async () => {
    if (pageNumber <= 1) return;
    setPageNumber(pageNumber - 1);
  };

  const onNextPage = async () => {
    if (!numPages || pageNumber >= numPages) return;
    setPageNumber(pageNumber + 1);
  };

  const onZoomIn = () => {
    setScale(Math.min(scale + 0.2, 3.0));
  };

  const onZoomOut = () => {
    setScale(Math.max(scale - 0.2, 0.5));
  };

  const downloadPdf = () => {
    if (pdfUrl) {
      const link = document.createElement("a");
      link.href = pdfUrl;
      link.download = "menu.pdf";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  if (!pdfjsLoaded) {
    return (
      <div
        style={{
          width,
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "#f8f9fa",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              width: "32px",
              height: "32px",
              border: "2px solid #e5e7eb",
              borderTopColor: "#0f9d58",
              borderRadius: "50%",
              animation: "spin 1s linear infinite",
              margin: "0 auto 12px",
            }}
          ></div>
          <p style={{ margin: 0, color: "#6b7280", fontSize: "14px" }}>
            Инициализация...
          </p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.spinner}></div>
        <p className={styles.loadingText}>Загрузка PDF меню...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.errorContainer}>
        <div className={styles.errorIcon}>📄</div>
        <p className={styles.errorText}>{error}</p>
        <div className={styles.errorActions}>
          <button onClick={downloadPdf} className={styles.downloadButton}>
            Скачать PDF
          </button>
        </div>
      </div>
    );
  }

  if (!numPages) {
    return (
      <div className={styles.noPdfContainer}>
        <div className={styles.noPdfIcon}>📋</div>
        <p className={styles.noPdfText}>PDF меню недоступно</p>
      </div>
    );
  }

  return (
    <div className={styles.pdfViewer} style={{ width, height }}>
      <div className={styles.controls}>
        <div className={styles.pageInfo}>
          Страница {pageNumber} из {numPages}
        </div>
        <div className={styles.navigation}>
          <button
            onClick={onPrevPage}
            disabled={pageNumber <= 1}
            className={styles.navButton}
          >
            ←
          </button>
          <button
            onClick={onNextPage}
            disabled={pageNumber >= numPages}
            className={styles.navButton}
          >
            →
          </button>
        </div>
        <div className={styles.zoomControls}>
          <button onClick={onZoomOut} className={styles.zoomButton}>
            -
          </button>
          <span className={styles.zoomLevel}>{Math.round(scale * 100)}%</span>
          <button onClick={onZoomIn} className={styles.zoomButton}>
            +
          </button>
        </div>
        <button onClick={downloadPdf} className={styles.downloadButton}>
          Скачать
        </button>
      </div>

      <div
        ref={containerRef}
        className={styles.pdfContainer}
        style={{ width: "100%", height: "calc(100% - 60px)" }}
      >
        <canvas ref={canvasRef} className={styles.pdfPage}></canvas>
      </div>
    </div>
  );
}
