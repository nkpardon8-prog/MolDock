'use client';

import { useState, useCallback } from 'react';
import { FileText, Download, Eye, EyeOff, Atom, FlaskConical, TestTube2, Box } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DynamicMol3DViewer } from '@/components/mol3d/dynamic-viewer';

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

const TYPE_LABELS: Record<FileType, string> = {
  receptor: 'Receptor',
  ligand: 'Ligand',
  docked: 'Docked',
};

function getExtension(name: string): string {
  const idx = name.lastIndexOf('.');
  return idx >= 0 ? name.slice(idx) : '';
}

function FileCard({ file }: { file: FileEntry }) {
  const [rawContent, setRawContent] = useState<string | null>(null);
  const [viewRaw, setViewRaw] = useState(false);
  const [view3D, setView3D] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fileContent, setFileContent] = useState<string | null>(null);

  const Icon = TYPE_ICONS[file.type] || FileText;
  const ext = getExtension(file.name);

  const fetchContent = useCallback(async () => {
    if (fileContent) return fileContent;
    setLoading(true);
    try {
      const { apiGetText } = await import('@/lib/api');
      const text = await apiGetText(file.downloadUrl);
      setFileContent(text);
      return text;
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, [file.downloadUrl, fileContent]);

  const handleDownload = useCallback(async () => {
    try {
      const { getAuthHeaders, API_URL } = await import('@/lib/api');
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_URL}${file.downloadUrl}`, { headers });
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
      // download failed
    }
  }, [file.downloadUrl, file.name]);

  const handleToggleRaw = useCallback(async () => {
    if (viewRaw) {
      setViewRaw(false);
      return;
    }
    const content = await fetchContent();
    if (content) {
      setRawContent(content);
      setViewRaw(true);
    }
  }, [viewRaw, fetchContent]);

  const handleToggle3D = useCallback(async () => {
    if (view3D) {
      setView3D(false);
      return;
    }
    const content = await fetchContent();
    if (content) {
      setView3D(true);
    }
  }, [view3D, fetchContent]);

  return (
    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <Icon className="h-5 w-5 text-[#8B949E]" />
          <div className="flex-1 min-w-0">
            <CardTitle className="truncate text-sm text-[#FAFAFA]">
              {file.name}
            </CardTitle>
            <p className="text-xs text-[#8B949E]">{TYPE_LABELS[file.type]}</p>
          </div>
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
        <div className="flex gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownload}
            className="border-[#2A2F3E] text-[#8B949E] hover:bg-[#2A2F3E] hover:text-[#FAFAFA]"
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            Download
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleToggle3D}
            disabled={loading}
            className="text-[#00D4AA] hover:text-[#00D4AA]/80 hover:bg-[#00D4AA]/10"
          >
            <Box className="h-3.5 w-3.5 mr-1" />
            {loading && !view3D ? 'Loading...' : view3D ? 'Hide 3D' : 'View 3D'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleToggleRaw}
            disabled={loading}
            className="text-[#8B949E] hover:text-[#FAFAFA]"
          >
            {viewRaw ? (
              <EyeOff className="h-3.5 w-3.5 mr-1" />
            ) : (
              <Eye className="h-3.5 w-3.5 mr-1" />
            )}
            {loading && !viewRaw ? 'Loading...' : viewRaw ? 'Hide Raw' : 'View Raw'}
          </Button>
        </div>

        {view3D && fileContent && (
          <div className="mt-3 rounded-lg border border-[#2A2F3E] overflow-hidden">
            <DynamicMol3DViewer
              proteinContent={file.type === 'receptor' ? fileContent : undefined}
              ligandContent={file.type !== 'receptor' ? fileContent : undefined}
              style={file.type === 'receptor' ? 'cartoon' : 'stick'}
              showSurface={false}
              showHbonds={false}
              bgColor="0x1a1a2e"
              width={700}
              height={400}
            />
          </div>
        )}

        {viewRaw && rawContent != null && (
          <pre className="mt-3 max-h-64 overflow-auto rounded bg-[#0E1117] p-3 text-xs text-[#8B949E] border border-[#2A2F3E] font-mono">
            {rawContent.slice(0, 10000)}
            {rawContent.length > 10000 && `\n\n... (showing first 10,000 of ${rawContent.length.toLocaleString()} characters)`}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}

export function FilePanel({ files }: FilePanelProps) {
  if (files.length === 0) {
    return (
      <div className="rounded-lg border border-[#2A2F3E] bg-[#1A1F2E] p-6 text-center text-sm text-[#8B949E]">
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
