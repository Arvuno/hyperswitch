use std::sync::Arc;

use error_stack::ResultExt;
use redis_interface::RedisConnectionPool;

use crate::{
    core::errors::{ApiErrorResponse, RouterResult},
    routes::app::SessionStateInfo,
};

fn get_redis_connection<A: SessionStateInfo>(state: &A) -> RouterResult<Arc<RedisConnectionPool>> {
    state
        .store()
        .get_redis_conn()
        .change_context(ApiErrorResponse::InternalServerError)
        .attach_printable("Failed to get redis connection")
}

pub async fn set_blocked_count_in_cache<A>(
    state: &A,
    cache_key: &str,
    value: i32,
    expiry: i64,
) -> RouterResult<()>
where
    A: SessionStateInfo + Sync,
{
    let redis_conn = get_redis_connection(state)?;

    redis_conn
        .set_key_with_expiry(&cache_key.into(), value, expiry)
        .await
        .change_context(ApiErrorResponse::InternalServerError)
}

pub async fn get_blocked_count_from_cache<A>(
    state: &A,
    cache_key: &str,
) -> RouterResult<Option<i32>>
where
    A: SessionStateInfo + Sync,
{
    let redis_conn = get_redis_connection(state)?;

    let value: Option<i32> = redis_conn
        .get_key(&cache_key.into())
        .await
        .change_context(ApiErrorResponse::InternalServerError)?;

    Ok(value)
}

pub async fn increment_blocked_count_in_cache<A>(
    state: &A,
    cache_key: &str,
    expiry: i64,
) -> RouterResult<()>
where
    A: SessionStateInfo + Sync,
{
    let redis_conn = get_redis_connection(state)?;

    let value: Option<i32> = redis_conn
        .get_key(&cache_key.into())
        .await
        .change_context(ApiErrorResponse::InternalServerError)?;

    let mut incremented_blocked_count: i32 = 1;

    if let Some(actual_value) = value {
        incremented_blocked_count = actual_value + 1;
    }

    redis_conn
        .set_key_with_expiry(&cache_key.into(), incremented_blocked_count, expiry)
        .await
        .change_context(ApiErrorResponse::InternalServerError)
}

pub async fn set_ip_only_blocked_count_in_cache<A>(
    state: &A,
    cache_key: &str,
    value: i32,
    expiry: i64,
) -> RouterResult<()>
where
    A: SessionStateInfo + Sync,
{
    let redis_conn = get_redis_connection(state)?;

    redis_conn
        .set_key_with_expiry(&cache_key.into(), value, expiry)
        .await
        .change_context(ApiErrorResponse::InternalServerError)
}

pub async fn get_ip_only_blocked_count_from_cache<A>(
    state: &A,
    cache_key: &str,
) -> RouterResult<Option<i32>>
where
    A: SessionStateInfo + Sync,
{
    let redis_conn = get_redis_connection(state)?;

    let value: Option<i32> = redis_conn
        .get_key(&cache_key.into())
        .await
        .change_context(ApiErrorResponse::InternalServerError)?;

    Ok(value)
}

pub async fn increment_ip_only_blocked_count_in_cache<A>(
    state: &A,
    cache_key: &str,
    expiry: i64,
) -> RouterResult<i32>
where
    A: SessionStateInfo + Sync,
{
    let redis_conn = get_redis_connection(state)?;

    let script = r#"
        local key = KEYS[1]
        local ttl = tonumber(ARGV[1])
        local current = redis.call('GET', key)
        if current then
            local new_val = redis.call('INCR', key)
            return new_val
        else
            redis.call('SET', key, 1, 'EX', ttl)
            return 1
        end
    "#;

    let result: i32 = redis_conn
        .evaluate_redis_script(script, vec![cache_key.to_string()], vec![expiry.to_string()])
        .await
        .change_context(ApiErrorResponse::InternalServerError)?;

    Ok(result)
}
