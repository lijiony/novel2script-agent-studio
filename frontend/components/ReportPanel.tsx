import type { ValidationReport } from "@/lib/api";

type Props = {
  report: ValidationReport | null;
  markdown: string;
};

export function ReportPanel({ report, markdown }: Props) {
  if (report) {
    return (
      <div>
        <div className="notice">
          <strong>{report.valid ? "校验通过" : "校验未通过"}</strong>
          <div>{report.summary}</div>
        </div>
        <div className="status-list" style={{ marginTop: 10 }}>
          {report.issues.map((issue, index) => (
            <div className="stage" key={`${issue.path}-${index}`}>
              <strong>
                {issue.path}: {issue.message}
              </strong>
              <span className={`badge ${issue.severity === "error" ? "failed" : ""}`}>
                {issue.severity}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (markdown) {
    return <div className="report">{markdown}</div>;
  }

  return <div className="notice">运行完成后，这里会显示校验报告。</div>;
}
