import { useEffect, useState } from 'react'
import './BookTranslator.css'

type Scope = 'all' | 'chapters' | 'pages' | 'range'
type Model = 'gpt' | 'claude' | 'kimi' | 'grok'
type OutputFormat = 'epub' | 'pdf'
type Mode = 'standard' | 'literary' | 'technical' | 'fast'

interface StructureUnit {
  id: string
  type: string
  source_path: string
  source_index: number
  text: string
}

interface BookStructure {
  title: string | null
  language: string
  format: 'epub' | 'pdf'
  spine: { id?: string; href?: string; page?: number }[]
  toc: { label: string; src: string }[]
  units: StructureUnit[]
}

interface JobStatus {
  job_id: string
  status: string
  progress_percent: number
  message: string
  output_file: string | null
  error: string | null
}

const LANGUAGES = [
  { code: 'hi', label: 'Hindi' },
  { code: 'te', label: 'Telugu' },
  { code: 'ta', label: 'Tamil' },
  { code: 'bn', label: 'Bengali' },
  { code: 'mr', label: 'Marathi' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'zh', label: 'Chinese' },
  { code: 'ja', label: 'Japanese' },
]

export default function BookTranslator() {
  const [file, setFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [structure, setStructure] = useState<BookStructure | null>(null)
  const [loading, setLoading] = useState(false)

  const [targetLanguage, setTargetLanguage] = useState('hi')
  const [scope, setScope] = useState<Scope>('all')
  const [model, setModel] = useState<Model>('gpt');
  const [outputFormat, setOutputFormat] = useState<OutputFormat>('epub')
  const [mode, setMode] = useState<Mode>('standard')
  const [selectedChapters, setSelectedChapters] = useState<string[]>([])
  const [pageStart, setPageStart] = useState<number | ''>('')
  const [pageEnd, setPageEnd] = useState<number | ''>('')

  const [status, setStatus] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<Array<{ original: string; translated: string | null }>>([])

  useEffect(() => {
    if (!jobId) return
    const interval = setInterval(async () => {
      const res = await fetch(`/api/status/${jobId}`)
      const data = await res.json()
      setStatus(data)
      if (data.status === 'done' || data.status === 'error') {
        clearInterval(interval)
        setLoading(false)
        // Fetch preview when done (translated-only, limit=3).
        const previewRes = await fetch(`/api/preview/${jobId}?limit=3`)
        if (previewRes.ok) {
          const previewData = await previewRes.json()
          setPreview(previewData.previews || [])
        }
      }
    }, 1500)
    return () => clearInterval(interval)
  }, [jobId])

  const handleUpload = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/upload', { method: 'POST', body: form })
    const data = await res.json()
    if (!res.ok) {
      setError(data.detail || 'Upload failed')
      setLoading(false)
      return
    }
    setJobId(data.job_id)
    const structRes = await fetch(`/api/structure/${data.job_id}`)
    const struct = await structRes.json()
    setStructure(struct)
    setLoading(false)
  }

  const toggleChapter = (href: string) => {
    setSelectedChapters((prev) =>
      prev.includes(href) ? prev.filter((h) => h !== href) : [...prev, href]
    )
  }

  const handleTranslate = async () => {
    if (!jobId) return
    setLoading(true)
    setError(null)
    const form = new FormData()
    form.append('target_language', targetLanguage)
    form.append('scope', scope)
    form.append('model', model)
    form.append('output_format', outputFormat)
    form.append('mode', mode)
    form.append('selected_chapters', selectedChapters.join(','))
    if (scope === 'range') {
      form.append('page_start', String(pageStart))
      form.append('page_end', String(pageEnd))
    }
    const res = await fetch(`/api/translate/${jobId}`, { method: 'POST', body: form })
    const data = await res.json()
    if (!res.ok) {
      setError(data.detail || 'Translation failed')
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!jobId) return
    window.location.href = `/api/download/${jobId}`
  }

  return (
    <div className="translator">
      <section className="card">
        <h2>1. Upload Book</h2>
        <input
          type="file"
          accept=".epub,.pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button onClick={handleUpload} disabled={!file || loading}>
          {loading && !structure ? 'Uploading…' : 'Upload'}
        </button>
      </section>

      {structure && (
        <section className="card">
          <h2>2. Select Content</h2>
          <div className="form-row">
            <label>Target language</label>
            <select value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)}>
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <label>Scope</label>
            <select value={scope} onChange={(e) => setScope(e.target.value as Scope)}>
              <option value="all">Whole book</option>
              {structure.format === 'epub' && <option value="chapters">Selected chapters</option>}
              {structure.format === 'pdf' && <option value="pages">Selected pages</option>}
              <option value="range">Page range</option>
            </select>
          </div>

          {scope === 'chapters' && (
            <div className="chapter-list">
              {structure.spine.map((item, idx) => (
                <label key={idx} className="chapter-item">
                  <input
                    type="checkbox"
                    checked={selectedChapters.includes(item.href || '')}
                    onChange={() => toggleChapter(item.href || '')}
                  />
                  {item.href || `Chapter ${idx + 1}`}
                </label>
              ))}
            </div>
          )}

          {scope === 'pages' && (
            <div className="form-row">
              <label>Selected pages (comma separated)</label>
              <input
                type="text"
                value={selectedChapters.join(',')}
                onChange={(e) => setSelectedChapters(e.target.value.split(',').map((s) => s.trim()))}
                placeholder="0,1,2"
              />
            </div>
          )}

          {scope === 'range' && (
            <div className="form-row range-row">
              <label>From</label>
              <input
                type="number"
                value={pageStart}
                onChange={(e) => setPageStart(e.target.value === '' ? '' : Number(e.target.value))}
              />
              <label>To</label>
              <input
                type="number"
                value={pageEnd}
                onChange={(e) => setPageEnd(e.target.value === '' ? '' : Number(e.target.value))}
              />
            </div>
          )}

          <div className="form-row">
            <label>Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value as Model)}>
              <option value="gpt">GPT (recommended)</option>
              <option value="grok">Grok</option>
              <option value="kimi">Kimi</option>
              {/* Claude is hidden because its deployment endpoint is currently not supported. */}
            </select>
          </div>

          <div className="form-row">
            <label>Output format</label>
            <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value as OutputFormat)}>
              <option value="epub">EPUB</option>
              <option value="pdf">PDF</option>
            </select>
          </div>

          <div className="form-row">
            <label>Mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
              <option value="standard">Standard</option>
              <option value="literary">Literary</option>
              <option value="technical">Technical</option>
              <option value="fast">Fast</option>
            </select>
          </div>

          <button onClick={handleTranslate} disabled={loading}>
            {loading && !status?.output_file ? 'Translating…' : 'Start Translation'}
          </button>
        </section>
      )}

      {status && (
        <section className="card status">
          <h2>3. Status</h2>
          <p>
            <strong>{status.status}</strong> — {status.progress_percent}%
          </p>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${status.progress_percent}%` }}
            />
          </div>
          <p className="progress-detail">
            {status.status === 'pending' && 'Waiting to start...'}
            {status.status === 'parsing' && 'Parsing book structure...'}
            {status.status === 'extracting_glossary' && 'Extracting translation glossary...'}
            {status.status === 'translating' && `Translating content... ${status.progress_percent}%`}
            {status.status === 'assembling' && 'Assembling output file...'}
            {status.status === 'done' && 'Translation complete!'}
            {status.status === 'error' && 'Translation failed.'}
          </p>
          {status.status === 'done' && status.output_file && (
            <button onClick={handleDownload}>Download {outputFormat.toUpperCase()}</button>
          )}
          {status.error && <p className="error">{status.error}</p>}

          {preview.length > 0 && (
            <div className="preview">
              <h3>Translated Preview</h3>
              {preview.map((p, idx) => (
                <div key={idx} className="preview-item">
                  <div className="preview-original">
                    <strong>Original:</strong> {p.original.slice(0, 300)}
                  </div>
                  <div className="preview-translated">
                    <strong>Translated:</strong> {p.translated ? p.translated.slice(0, 500) : '—'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  )
}
