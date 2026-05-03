import { useState } from 'react';
import type { AgentCreatePayload } from '../types/agent';
import { createAgent } from '../api/agents';
import { Nav } from '../components/Nav';
import type { Page } from '../components/Nav';

interface Props {
  page: Page;
  onNavigate: (page: Page) => void;
}

interface ConfigEntry {
  key: string;
  value: string;
}

interface FormState {
  name: string;
  version: string;
  description: string;
  image: string;
  port: string;
  secretName: string;
  configEntries: ConfigEntry[];
  requestsCpu: string;
  requestsMemory: string;
  limitsCpu: string;
  limitsMemory: string;
  minReplicas: string;
  maxReplicas: string;
  targetCpu: string;
}

const EMPTY: FormState = {
  name: '',
  version: '',
  description: '',
  image: '',
  port: '',
  secretName: '',
  configEntries: [{ key: '', value: '' }],
  requestsCpu: '',
  requestsMemory: '',
  limitsCpu: '',
  limitsMemory: '',
  minReplicas: '',
  maxReplicas: '',
  targetCpu: '',
};

function buildPayload(f: FormState): AgentCreatePayload {
  const config = Object.fromEntries(
    f.configEntries
      .filter((e) => e.key.trim() && e.value.trim())
      .map((e) => [e.key.trim(), e.value.trim()]),
  );
  const requests =
    f.requestsCpu || f.requestsMemory
      ? {
          ...(f.requestsCpu && { cpu: f.requestsCpu }),
          ...(f.requestsMemory && { memory: f.requestsMemory }),
        }
      : undefined;
  const limits =
    f.limitsCpu || f.limitsMemory
      ? {
          ...(f.limitsCpu && { cpu: f.limitsCpu }),
          ...(f.limitsMemory && { memory: f.limitsMemory }),
        }
      : undefined;

  return {
    name: f.name.trim(),
    version: f.version.trim(),
    ...(f.description.trim() && { description: f.description.trim() }),
    spec: {
      image: f.image.trim(),
      ...(f.port && { port: parseInt(f.port, 10) }),
      ...(f.secretName.trim() && { secret_name: f.secretName.trim() }),
      ...(Object.keys(config).length > 0 && { config }),
      ...((requests || limits) && { resources: { requests, limits } }),
      ...((f.minReplicas || f.maxReplicas || f.targetCpu) && {
        scaling: {
          ...(f.minReplicas && { min_replicas: parseInt(f.minReplicas, 10) }),
          ...(f.maxReplicas && { max_replicas: parseInt(f.maxReplicas, 10) }),
          ...(f.targetCpu && { target_cpu_utilization_percentage: parseInt(f.targetCpu, 10) }),
        },
      }),
    },
  };
}

const inputCls =
  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500';

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-gray-600">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      {children}
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
      {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
    </div>
  );
}

export function DeployPage({ page, onNavigate }: Props) {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function setField(field: keyof FormState) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setForm((prev) => ({ ...prev, [field]: e.target.value }));
      setSuccess(null);
      setError(null);
    };
  }

  function setConfigKey(i: number, value: string) {
    setForm((prev) => {
      const entries = [...prev.configEntries];
      entries[i] = { ...entries[i], key: value };
      return { ...prev, configEntries: entries };
    });
  }

  function setConfigValue(i: number, value: string) {
    setForm((prev) => {
      const entries = [...prev.configEntries];
      entries[i] = { ...entries[i], value };
      return { ...prev, configEntries: entries };
    });
  }

  function addConfigEntry() {
    setForm((prev) => ({
      ...prev,
      configEntries: [...prev.configEntries, { key: '', value: '' }],
    }));
  }

  function removeConfigEntry(i: number) {
    setForm((prev) => ({
      ...prev,
      configEntries: prev.configEntries.filter((_, idx) => idx !== i),
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSuccess(null);
    setError(null);
    try {
      const agent = await createAgent(buildPayload(form));
      setSuccess(`"${agent.name} v${agent.version}" deployed successfully.`);
      setForm(EMPTY);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-slate-900 border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white tracking-tight">Agent Registry</h1>
            <p className="text-sm text-slate-400 mt-0.5">Deploy a new agent to the cluster</p>
          </div>
          <Nav current={page} onNavigate={onNavigate} />
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8">
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Basic info */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <SectionHeader title="Basic Info" />
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Field label="Name" required>
                  <input
                    className={inputCls}
                    required
                    value={form.name}
                    onChange={setField('name')}
                    placeholder="my-agent"
                  />
                </Field>
                <Field label="Version" required>
                  <input
                    className={inputCls}
                    required
                    value={form.version}
                    onChange={setField('version')}
                    placeholder="0.1.0"
                  />
                </Field>
              </div>
              <Field label="Description">
                <textarea
                  className={`${inputCls} resize-none`}
                  rows={2}
                  value={form.description}
                  onChange={setField('description')}
                  placeholder="What does this agent do?"
                />
              </Field>
            </div>
          </div>

          {/* Container */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <SectionHeader
              title="Container"
              subtitle="The OCI image and runtime settings for this agent."
            />
            <div className="space-y-4">
              <Field label="Image" required>
                <input
                  className={inputCls}
                  required
                  value={form.image}
                  onChange={setField('image')}
                  placeholder="registry.agent-system.svc.cluster.local:5000/my-agent:0.1.0"
                />
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Port">
                  <input
                    className={inputCls}
                    type="number"
                    min={1}
                    max={65535}
                    value={form.port}
                    onChange={setField('port')}
                    placeholder="8080"
                  />
                </Field>
                <Field label="Secret Name">
                  <input
                    className={inputCls}
                    value={form.secretName}
                    onChange={setField('secretName')}
                    placeholder="my-agent-secrets"
                  />
                </Field>
              </div>
            </div>
          </div>

          {/* Config */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <SectionHeader
              title="Config"
              subtitle="Environment variables injected into the agent container."
            />
            <div className="space-y-2">
              {form.configEntries.map((entry, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    className={`${inputCls} flex-1 font-mono`}
                    value={entry.key}
                    onChange={(e) => setConfigKey(i, e.target.value)}
                    placeholder="KEY"
                  />
                  <input
                    className={`${inputCls} flex-[2]`}
                    value={entry.value}
                    onChange={(e) => setConfigValue(i, e.target.value)}
                    placeholder="value"
                  />
                  <button
                    type="button"
                    onClick={() => removeConfigEntry(i)}
                    disabled={form.configEntries.length === 1}
                    className="px-2 text-gray-400 hover:text-red-500 disabled:opacity-30 transition-colors"
                    aria-label="Remove entry"
                  >
                    ×
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addConfigEntry}
                className="mt-1 text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors"
              >
                + Add entry
              </button>
            </div>
          </div>

          {/* Resources */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <SectionHeader title="Resources" subtitle="All fields are optional." />
            <div className="grid grid-cols-2 gap-4">
              <Field label="CPU Request">
                <input
                  className={inputCls}
                  value={form.requestsCpu}
                  onChange={setField('requestsCpu')}
                  placeholder="100m"
                />
              </Field>
              <Field label="Memory Request">
                <input
                  className={inputCls}
                  value={form.requestsMemory}
                  onChange={setField('requestsMemory')}
                  placeholder="128Mi"
                />
              </Field>
              <Field label="CPU Limit">
                <input
                  className={inputCls}
                  value={form.limitsCpu}
                  onChange={setField('limitsCpu')}
                  placeholder="500m"
                />
              </Field>
              <Field label="Memory Limit">
                <input
                  className={inputCls}
                  value={form.limitsMemory}
                  onChange={setField('limitsMemory')}
                  placeholder="256Mi"
                />
              </Field>
            </div>
          </div>

          {/* Scaling */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <SectionHeader title="Scaling" subtitle="All fields are optional." />
            <div className="grid grid-cols-3 gap-4">
              <Field label="Min Replicas">
                <input
                  className={inputCls}
                  type="number"
                  min={1}
                  value={form.minReplicas}
                  onChange={setField('minReplicas')}
                  placeholder="1"
                />
              </Field>
              <Field label="Max Replicas">
                <input
                  className={inputCls}
                  type="number"
                  min={1}
                  value={form.maxReplicas}
                  onChange={setField('maxReplicas')}
                  placeholder="3"
                />
              </Field>
              <Field label="Target CPU %">
                <input
                  className={inputCls}
                  type="number"
                  min={1}
                  max={100}
                  value={form.targetCpu}
                  onChange={setField('targetCpu')}
                  placeholder="80"
                />
              </Field>
            </div>
          </div>

          {success && (
            <div className="rounded-xl border border-green-200 bg-green-50 px-5 py-4 text-sm text-green-700">
              <strong>Deployed:</strong> {success}
            </div>
          )}
          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
              <strong>Error:</strong> {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl transition-colors"
          >
            {submitting ? 'Deploying…' : 'Deploy Agent'}
          </button>
        </form>
      </main>
    </div>
  );
}
