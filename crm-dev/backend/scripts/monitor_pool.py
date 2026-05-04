#!/usr/bin/env python3
"""
Database Connection Pool Monitoring Utility

Usage:
    python monitor_pool.py --url http://localhost:8000 --interval 5
    python monitor_pool.py --url https://crm.pticasinicafamily.ru --interval 10
"""

import asyncio
import aiohttp
import argparse
from datetime import datetime
from typing import Optional, Dict, Any
import json
import sys


class PoolMonitor:
    """Monitor database connection pool health"""
    
    def __init__(self, base_url: str, health_endpoint: str = "/health/db"):
        self.base_url = base_url.rstrip("/")
        self.health_endpoint = health_endpoint
        self.url = f"{self.base_url}{self.health_endpoint}"
        self.consecutive_warnings = 0
    
    async def fetch_pool_metrics(self) -> Optional[Dict[str, Any]]:
        """Fetch pool metrics from health endpoint"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"❌ Health endpoint returned {response.status}")
                        return None
        except aiohttp.ClientError as e:
            print(f"❌ Connection error: {e}")
            return None
        except asyncio.TimeoutError:
            print(f"❌ Request timeout")
            return None
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return None
    
    def _format_metrics(self, metrics: Dict[str, Any]) -> str:
        """Format metrics for display"""
        pool = metrics.get("pool_metrics", {})
        
        status = metrics.get("status", "unknown")
        response_time = metrics.get("response_time", 0)
        
        if not pool:
            return f"Status: {status}, Response: {response_time}ms"
        
        checked_out = pool.get("connections_checkedout", 0)
        pool_size = pool.get("pool_size", 0)
        overflow = pool.get("overflow_size", 0)
        utilization = pool.get("utilization_percent", 0)
        
        # Color coding based on utilization
        if utilization >= 90:
            status_emoji = "🔴"  # Critical
            color = "\033[91m"  # Red
        elif utilization >= 75:
            status_emoji = "🟠"  # Warning
            color = "\033[93m"  # Yellow
        elif utilization >= 50:
            status_emoji = "🟡"  # Caution
            color = "\033[94m"  # Blue
        else:
            status_emoji = "🟢"  # Healthy
            color = "\033[92m"  # Green
        
        reset = "\033[0m"
        
        line = (
            f"{status_emoji} [{color}{status.upper()}{reset}] "
            f"Pool: {checked_out}/{pool_size} | "
            f"Overflow: {overflow} | "
            f"Util: {utilization:.1f}% | "
            f"Response: {response_time}ms"
        )
        
        return line
    
    def _check_health(self, metrics: Dict[str, Any]) -> bool:
        """Check if pool health is acceptable"""
        if metrics.get("status") != "healthy" and metrics.get("status") != "warning":
            return False
        
        pool = metrics.get("pool_metrics", {})
        if not pool:
            return True
        
        utilization = pool.get("utilization_percent", 0)
        
        # Alert conditions
        if utilization >= 90:
            return False
        
        return True
    
    async def monitor_continuous(self, interval: int = 5, duration: Optional[int] = None):
        """Continuously monitor pool health"""
        print(f"🔍 Monitoring database connection pool")
        print(f"   Endpoint: {self.url}")
        print(f"   Interval: {interval}s")
        if duration:
            print(f"   Duration: {duration}s")
        print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 100)
        
        start_time = datetime.now()
        iteration = 0
        
        while True:
            iteration += 1
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            metrics = await self.fetch_pool_metrics()
            
            if metrics:
                formatted = self._format_metrics(metrics)
                is_healthy = self._check_health(metrics)
                
                if not is_healthy:
                    self.consecutive_warnings += 1
                    if self.consecutive_warnings == 1:
                        print(f"\n⚠️  ALERT: Pool health degraded!")
                    print(f"[{timestamp}] {formatted}")
                else:
                    if self.consecutive_warnings > 0:
                        print(f"✅ Recovery after {self.consecutive_warnings} warnings")
                        self.consecutive_warnings = 0
                    print(f"[{timestamp}] {formatted}")
            
            # Check duration limit
            if duration:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= duration:
                    print("-" * 100)
                    print(f"✓ Monitoring completed after {duration}s ({iteration} samples)")
                    break
            
            # Wait for next interval
            try:
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                print("\n\n✓ Monitoring stopped by user")
                break
    
    async def single_check(self):
        """Perform a single health check"""
        print(f"Checking: {self.url}")
        metrics = await self.fetch_pool_metrics()
        
        if metrics:
            print(json.dumps(metrics, indent=2))
            return True
        else:
            print("❌ Failed to fetch metrics")
            return False


async def main():
    parser = argparse.ArgumentParser(
        description="Monitor database connection pool health",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python monitor_pool.py --url http://localhost:8000
  python monitor_pool.py --url https://crm.pticasinicafamily.ru --interval 10
  python monitor_pool.py --url http://localhost:8000 --interval 2 --duration 60
  python monitor_pool.py --url http://localhost:8000 --check
        """
    )
    
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the application (e.g., http://localhost:8000)"
    )
    
    parser.add_argument(
        "--endpoint",
        default="/health/db",
        help="Health endpoint path (default: /health/db)"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Check interval in seconds (default: 5)"
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        help="Monitor for N seconds then exit (optional)"
    )
    
    parser.add_argument(
        "--check",
        action="store_true",
        help="Single health check and exit"
    )
    
    args = parser.parse_args()
    
    monitor = PoolMonitor(args.url, args.endpoint)
    
    if args.check:
        success = await monitor.single_check()
        sys.exit(0 if success else 1)
    else:
        await monitor.monitor_continuous(args.interval, args.duration)


if __name__ == "__main__":
    asyncio.run(main())
