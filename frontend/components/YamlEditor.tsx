"use client";

import Editor, { type Monaco, type OnMount } from "@monaco-editor/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { configureMonacoYaml } from "monaco-yaml";

type Props = {
  value: string;
  schema: Record<string, unknown> | null;
  onChange: (value: string) => void;
};

export function YamlEditor({ value, schema, onChange }: Props) {
  const [fallback, setFallback] = useState(false);
  const monacoRef = useRef<Monaco | null>(null);
  const yamlConfigRef = useRef<{ dispose: () => void } | null>(null);
  const schemaUri = useMemo(() => "inmemory://model/script.schema.json", []);

  useEffect(() => {
    const monaco = monacoRef.current;
    if (!monaco || !schema) {
      return;
    }
    try {
      yamlConfigRef.current?.dispose();
      yamlConfigRef.current = configureMonacoYaml(monaco, {
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
    return () => {
      yamlConfigRef.current?.dispose();
      yamlConfigRef.current = null;
    };
  }, [schema, schemaUri]);

  const handleMount: OnMount = (_editor, monaco) => {
    monacoRef.current = monaco;
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
        height="100%"
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
