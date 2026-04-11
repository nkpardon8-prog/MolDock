'use client';

import { useState, useCallback } from 'react';
import { FileText, Download, Eye, EyeOff, Atom, FlaskConical, TestTube2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

type FileType = 'receptor' | 'ligand' | 'docked';

interface FileEntry {
  name: string;
  type: FileType;
  downloadUrl: string;
  path: string;
}

interface FilePanelProps {
  files: FileEntry[];
}

const TYPE_ICONS: Record<FileType, typeof Atom> = {
  receptor: Atom,
  ligand: FlaskConical,
  docked: TestTube2,
};

const TYPE_COLORS: Record<FileType, string> = {
  receptor: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  ligand: 'bg-teal-500/20 text-teal-400 border-teal-500/30',
  docked: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
};

function getExtension(name: string): string {
  const idx = name.lastIndexOf('.');
  return idx >= 0 ? name.slice(idx) : '';
}

function FileCard({ file }: { file: FileEntry }) {
  const [rawContent, setRawContent] = useState<string | null>(null);
  const [viewRaw, setViewRaw] = useState(false);
  const [loading, setLoading] = useState(false);

  const Icon = TYPE_ICONS[file.type] || FileText;
  const ext = getExtension(file.name);

  const handleDownload = useCallback(async () => {
    try {
      const response = await fetch(file.downloadUrl);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // download failed silently
    }
  }, [file.downloadUrl, file.name]);

  const handleToggleRaw = useCallback(async () => {
    if (viewRaw) {
      setViewRaw(false);
      return;
    }

    if (rawContent != null) {
      setViewRaw(true);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(file.downloadUrl);
      const text = await response.text();
      setRawContent(text);
      setViewRaw(true);
    } catch {
      setRawContent('Failed to load file content.');
      setViewRaw(true);
    } finally {
      setLoading(false);
    }
  }, [viewRaw, rawContent, file.downloadUrl]);

  return (
    <Card className="border-zinc-700 bg-zinc-900">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <Icon className="h-5 w-5 text-zinc-400" />
          <CardTitle className="flex-1 truncate text-sm text-zinc-100">
            {file.name}
          </CardTitle>
          {ext && (
            <span
              className={`rounded border px-1.5 py-0.5 text-xs font-mono ${TYPE_COLORS[file.type]}`}
            >
              {ext}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownload}
            className="border-zinc-600 text-zinc-300 hover:bg-zinc-800"
          >
            <Download className="h-3.5 w-3.5" />
            Download
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleToggleRaw}
            disabled={loading}
            className="text-zinc-400 hover:text-zinc-200"
          >
            {viewRaw ? (
              <EyeOff className="h-3.5 w-3.5" />
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
            {loading ? 'Loading...' : viewRaw ? 'Hide Raw' : 'View Raw'}
          </Button>
        </div>
        {viewRaw && rawContent != null && (
          <pre className="mt-3 max-h-64 overflow-auto rounded bg-zinc-950 p-3 text-xs text-zinc-300 border border-zinc-700">
            {rawContent}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}

export function FilePanel({ files }: FilePanelProps) {
  if (files.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-6 text-center text-sm text-zinc-500">
        No files available.
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {files.map((file) => (
        <FileCard key={file.path} file={file} />
      ))}
    </div>
  );
}
