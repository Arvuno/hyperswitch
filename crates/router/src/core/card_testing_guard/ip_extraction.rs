use std::net::IpAddr;

use actix_web::http::header::HeaderMap;
use router_env::logger;

/// Extract the real client IP from request headers, respecting X-Forwarded-For
/// and trusted proxy configuration.
///
/// Walks X-Forwarded-For from RIGHT to LEFT, skipping trusted proxies.
/// The rightmost IP is set by the last trusted proxy; the first untrusted
/// IP from the right is the real client IP.
pub fn extract_client_ip(
    headers: &HeaderMap,
    connection_info: &actix_web::dev::ConnectionInfo,
    trusted_proxies: &[String],
) -> Option<IpAddr> {
    if let Some(xff) = headers.get("X-Forwarded-For").and_then(|v| v.to_str().ok()) {
        let ips: Vec<&str> = xff.split(',').map(|s| s.trim()).collect();

        for ip_str in ips.iter().rev() {
            if ip_str.is_empty() {
                continue;
            }

            match ip_str.parse::<IpAddr>() {
                Ok(ip) => {
                    let ip_str_normalized = ip.to_string();
                    if !trusted_proxies.contains(&ip_str_normalized) {
                        return Some(ip);
                    }
                }
                Err(_) => {
                    logger::warn!("Invalid IP in X-Forwarded-For header: {}", ip_str);
                    continue;
                }
            }
        }
    }

    connection_info
        .realip_remote_addr()
        .and_then(|ip_str| ip_str.parse::<IpAddr>().ok())
}

#[cfg(test)]
mod tests {
    use super::*;
}
