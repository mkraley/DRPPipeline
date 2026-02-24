/**
 * Scoreboard - Displays the tree of visited URLs with status (OK, 404, DL).
 */
import { useCollectorStore, type ScoreboardNode } from "../store";

function ScoreboardNodeItem({ node }: { node: ScoreboardNode }) {
  const isDownload = node.is_download === true;

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
      {isDownload ? (
        <span className="scoreboard-row-content status-download" title={node.url}>
          {node.filename || displayShort}
        </span>
      ) : (
        <a
          href={node.url}
          target="_blank"
          rel="noopener noreferrer"
          className={`url-link scoreboard-row-content ${
            node.status_label.includes("404")
              ? "status-404"
              : node.is_dupe
                ? "status-dupe"
                : "status-ok"
          }`}
          title={node.url}
        >
          {displayShort}
        </a>
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
            <ScoreboardNodeItem key={c.idx} node={c} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function Scoreboard() {
  const { scoreboard, refreshScoreboard } = useCollectorStore();

  return (
    <div className="scoreboard">
      <h3>
        Scoreboard
        <button
          type="button"
          className="btn-refresh"
          onClick={() => refreshScoreboard()}
          title="Refresh scoreboard"
        >
          Refresh
        </button>
      </h3>
      {scoreboard.length === 0 ? (
        <p>
          <em>No pages yet.</em>
        </p>
      ) : (
        <ul>
          {scoreboard.map((n) => (
            <ScoreboardNodeItem key={n.idx} node={n} />
          ))}
        </ul>
      )}
    </div>
  );
}
