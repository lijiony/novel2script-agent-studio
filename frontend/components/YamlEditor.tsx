"use client";

import Editor, { type OnMount } from "@monaco-editor/react";
import { useMemo, useState } from "react";
import { configureMonacoYaml } from "monaco-yaml";

type Props = {
  value: string;
  schema: Record<string, unknown> | null;
  onChange: (value: string) => void;
};

export function YamlEditor({ value, schema, onChange }: Props) {
  const [fallback, setFallback] = useState(false);
  const schemaUri = useMemo(() => "inmemory://model/script.schema.json", []);

  const handleMount: OnMount = (_editor, monaco) => {
    if (!schema) {
      return;
    }
    try {
      configureMonacoYaml(monaco, {
        enableSchemaRequest: false,
        schemas: [
          {
            uri: schemaUri,
            fileMatch: ["script.yaml"],
            schema,
          },
        ],
      });
    } catch {
      setFallback(true);
    }
  };

  if (fallback) {
    return (
      <textarea
        className="fallback-editor"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        spellCheck={false}
      />
    );
  }

  return (
    <div className="editor-wrap">
      <Editor
        height="520px"
        defaultLanguage="yaml"
        path="script.yaml"
        value={value}
        theme="vs"
        onMount={handleMount}
        onChange={(nextValue) => onChange(nextValue ?? "")}
        loading={<textarea className="fallback-editor" value={value} readOnly />}
        options={{
          minimap: { enabled: false },
          wordWrap: "on",
          fontSize: 13,
          scrollBeyondLastLine: false,
          automaticLayout: true,
        }}
      />
    </div>
  );
}
