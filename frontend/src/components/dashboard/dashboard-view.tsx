// ---------------------------------------------------------------------------
// DashboardView — grid layout with health cards and metrics
// ---------------------------------------------------------------------------

import { MessageSquare, Hash, Wifi, WifiOff } from 'lucide-react';
import { useHealthPoll } from '@/hooks/use-health-poll';
import { useChatStore } from '@/stores/chat-store';
import { HealthCard } from './health-card';
import { MetricsCard } from './metrics-card';

export function DashboardView() {
  const { services, isConnected } = useHealthPoll();
  const sessions = useChatStore((s) => s.sessions);

  const totalSessions = sessions.length;
  // Use messageCount (server-reported) rather than messages.length — most
  // sessions are summary-only until the user actively opens them, so
  // messages.length would undercount the real total.
  const totalMessages = sessions.reduce((sum, s) => sum + s.messageCount, 0);

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-1">System Health</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Live status of backend services
        </p>
      </div>

      {/* Health Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {services.map((service) => (
          <HealthCard key={service.name} service={service} />
        ))}
      </div>

      {/* Metrics */}
      <div>
        <h2 className="text-xl font-semibold mb-1">Metrics</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Local session statistics
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <MetricsCard
          icon={Hash}
          value={totalSessions}
          label="Total Sessions"
        />
        <MetricsCard
          icon={MessageSquare}
          value={totalMessages}
          label="Total Messages"
        />
        <MetricsCard
          icon={isConnected ? Wifi : WifiOff}
          value={isConnected ? 'Connected' : 'Disconnected'}
          label="Connection Status"
        />
      </div>
    </div>
  );
}
