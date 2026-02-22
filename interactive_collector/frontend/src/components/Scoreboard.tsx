/**
 * Scoreboard - Displays the tree of visited URLs with status (OK, 404, DL).
 *
 * Shows checkboxes for pages that can be saved as PDF. Save button triggers
 * the save endpoint with checked indices.
 */
import { useCallback } from "react";
import { useCollectorStore, type ScoreboardNode } from "../store";

function walkScoreboard(nodes: ScoreboardNode[]): ScoreboardNode[] {
  const flat: ScoreboardNode[] = [];
  function walk(n: ScoreboardNode[]) {
    for (const node of n) {
      flat.push(node);
      if (node.children?.length) walk(node.children);
    }
  }
  walk(nodes);
  return flat;
}

function downloadBlob(blob: Blob, filename: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function ScoreboardNodeItem({
  node,
  sourceUrl,
  onLinkClick,
}: {
  node: ScoreboardNode;
  sourceUrl: string;
  onLinkClick: (url: string, referrer: string | null, fromScoreboard: boolean) => void;
}) {
  const { checkedIndices, setChecked } = useCollectorStore();
  const isChecked = checkedIndices.has(node.idx);
  const isOk = node.status_label.includes("OK");
  const isDownload = node.is_download === true;

  // Checkbox logic: OK non-dupe (dupes not checkable)
  const canCheck = isOk && !isDownload && !node.is_dupe;
  const handleChange = useCallback(() => {
    if (canCheck) setChecked(node.idx, !isChecked);
  }, [canCheck, node.idx, isChecked, setChecked]);

  const displayText =
    (node.title && typeof node.title === "string" && node.title.trim())
      ? node.title.trim()
      : (node.url || "(no url)");
  const displayShort =
    displayText.length > 80 ? displayText.slice(0, 80) + "..." : displayText;
  const statusDisplay = isDownload
    ? `${node.status_label} ${node.extension || ""}`.trim()
    : node.is_dupe
      ? `${node.status_label} (dupe)`
      : node.status_label;

  return (
    <li>
      <div className="scoreboard-row">
      {(canCheck ? (
        <input
          type="checkbox"
          className="scoreboard-cb"
          checked={isChecked}
          onChange={handleChange}
        />
      ) : (
        <span className="scoreboard-cb-spacer" aria-hidden="true" />
      ))}
      {isDownload ? (
        <span className="scoreboard-row-content status-download" title={node.url}>
          {node.filename || displayShort}
        </span>
      ) : (
        <button
          type="button"
          className={`url-link scoreboard-row-content ${
            node.status_label.includes("404")
              ? "status-404"
              : node.is_dupe
                ? "status-dupe"
                : "status-ok"
          }`}
          onClick={() => onLinkClick(node.url, node.referrer, true)}
          title={node.url}
        >
          {displayShort}
        </button>
      )}
      <span
        className={`scoreboard-status ${
          isDownload ? "status-download" : node.status_label.includes("404") ? "status-404" : node.is_dupe ? "status-dupe" : "status-ok"
        }`}
      >
        ({statusDisplay})
      </span>
      </div>
      {node.children && node.children.length > 0 && (
        <ul className="scoreboard-children">
          {node.children.map((c) => (
            <ScoreboardNodeItem
              key={c.idx}
              node={c}
              sourceUrl={sourceUrl}
              onLinkClick={onLinkClick}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function Scoreboard() {
  const { scoreboard, sourceUrl, loadLinked, refreshScoreboard, clearScoreboard } = useCollectorStore();

  const onLinkClick = useCallback(
    (url: string, referrer: string | null, fromScoreboard: boolean) => {
      loadLinked(url, referrer, fromScoreboard);
    },
    [loadLinked]
  );

  return (
    <div className="scoreboard">
      <h3>
        Scoreboard
        <button
          type="button"
          className="btn-refresh"
          onClick={() => refreshScoreboard()}
          title="Refresh scoreboard (e.g. after saving from extension)"
        >
          Refresh
        </button>
        <button
          type="button"
          className="btn-refresh btn-clear"
          onClick={() => clearScoreboard()}
          title="Clear scoreboard"
          disabled={scoreboard.length === 0}
        >
          Clear
        </button>
        <button
          type="button"
          className="btn-refresh btn-export"
          onClick={() => {
            const json = JSON.stringify(scoreboard, null, 2);
            downloadBlob(new Blob([json], { type: "application/json" }), "scoreboard.json");
          }}
          title="Export scoreboard as JSON"
          disabled={scoreboard.length === 0}
        >
          Export JSON
        </button>
        <button
          type="button"
          className="btn-refresh btn-export"
          onClick={() => {
            const flat = walkScoreboard(scoreboard);
            const header = "url,status,referrer\n";
            const rows = flat.map(
              (n) =>
                `"${(n.url || "").replace(/"/g, '""')}","${(n.status_label || "").replace(/"/g, '""')}","${((n.referrer || "").replace(/"/g, '""'))}"`
            );
            downloadBlob(new Blob([header + rows.join("\n")], { type: "text/csv" }), "visited_urls.csv");
          }}
          title="Export visited URLs as CSV (for pipeline input)"
          disabled={scoreboard.length === 0}
        >
          Export CSV
        </button>
      </h3>
      {scoreboard.length === 0 ? (
        <p>
          <em>No pages yet.</em>
        </p>
      ) : (
        <ul>
          {scoreboard.map((n) => (
            <ScoreboardNodeItem key={n.idx} node={n} sourceUrl={sourceUrl} onLinkClick={onLinkClick} />
          ))}
        </ul>
      )}
    </div>
  );
}
