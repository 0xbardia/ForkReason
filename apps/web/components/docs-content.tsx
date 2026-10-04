"use client";

import { DOC_INDEX, DOC_PAGES, findDocPage, type DocBlock, type DocPage } from "@/lib/docs-data";

export { DOC_INDEX, DOC_PAGES, findDocPage };
export type { DocBlock, DocPage };

export function DocContent({ page }: { page: DocPage }) {
  return (
    <>
      <header className="docs-article-head">
        <h1 className="heading-2">{page.title}</h1>
        <p className="lead">{page.summary}</p>
      </header>
      {page.blocks.map((block, index) => (
        <DocBlockView key={index} block={block} />
      ))}
    </>
  );
}

function DocBlockView({ block }: { block: DocBlock }) {
  switch (block.kind) {
    case "h3":
      return <h2 className="docs-h3">{block.text}</h2>;
    case "p":
      return <p className="docs-p">{block.text}</p>;
    case "ul":
      return (
        <ul className="docs-list">
          {block.items?.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol className="docs-list docs-list-ol">
          {block.items?.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ol>
      );
    case "code":
      return (
        <pre className="docs-code" data-lang={block.lang}>
          <code>{block.text}</code>
        </pre>
      );
    case "note":
      return <p className="docs-note">{block.text}</p>;
    case "badge":
      return (
        <p>
          <span className={`badge badge-${block.tone}`}>{block.text}</span>
        </p>
      );
    case "table":
      return (
        <div className="docs-table" role="table">
          <div className="docs-table-row docs-table-head" role="row">
            {block.header?.map((cell) => (
              <span key={cell} role="columnheader">
                {cell}
              </span>
            ))}
          </div>
          {block.rows?.map((row, i) => (
            <div key={i} className="docs-table-row" role="row">
              {row.map((cell, j) => (
                <span key={j} role="cell">
                  {cell}
                </span>
              ))}
            </div>
          ))}
        </div>
      );
    default:
      return null;
  }
}
