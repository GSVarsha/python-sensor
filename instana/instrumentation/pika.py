# coding: utf-8
# (c) Copyright IBM Corp. 2021
# (c) Copyright Instana Inc. 2021


from __future__ import absolute_import

import wrapt
import opentracing
import types

from ..log import logger
from ..singletons import tracer
from ..util.traceutils import get_active_tracer

try:
    import pika


    def _extract_broker_tags(span, conn):
        span.set_tag("address", "%s:%d" % (conn.params.host, conn.params.port))


    def _extract_publisher_tags(span, conn, exchange, routing_key):
        _extract_broker_tags(span, conn)

        span.set_tag("sort", "publish")
        span.set_tag("key", routing_key)
        span.set_tag("exchange", exchange)


    def _extract_consumer_tags(span, conn, queue):
        _extract_broker_tags(span, conn)

        span.set_tag("sort", "consume")
        span.set_tag("queue", queue)


    @wrapt.patch_function_wrapper('pika.channel', 'Channel.basic_publish')
    def basic_publish_with_instana(wrapped, instance, args, kwargs):
        def _bind_args(exchange, routing_key, body, properties=None, *args, **kwargs):
            return (exchange, routing_key, body, properties, args, kwargs)

        active_tracer = get_active_tracer()

        if active_tracer is None:
            return wrapped(*args, **kwargs)

        (exchange, routing_key, body, properties, args, kwargs) = (_bind_args(*args, **kwargs))

        with tracer.start_active_span("rabbitmq", child_of=active_tracer.active_span) as scope:
            try:
                _extract_publisher_tags(scope.span,
                                        conn=instance.connection,
                                        routing_key=routing_key,
                                        exchange=exchange)
            except:
                logger.debug("publish_with_instana: ", exc_info=True)

            # context propagation
            properties = properties or pika.BasicProperties()
            properties.headers = properties.headers or {}

            tracer.inject(scope.span.context, opentracing.Format.HTTP_HEADERS, properties.headers,
                          disable_w3c_trace_context=True)
            args = (exchange, routing_key, body, properties) + args

            try:
                rv = wrapped(*args, **kwargs)
            except Exception as e:
                scope.span.log_exception(e)
                raise
            else:
                return rv


    def basic_get_with_instana(wrapped, instance, args, kwargs):
        def _bind_args(*args, **kwargs):
            args = list(args)
            queue = kwargs.pop('queue', None) or args.pop(0)
            callback = kwargs.pop('callback', None) or kwargs.pop('on_message_callback', None) or args.pop(0)
            return (queue, callback, tuple(args), kwargs)

        queue, callback, args, kwargs = _bind_args(*args, **kwargs)

        def _cb_wrapper(channel, method, properties, body):
            parent_span = tracer.extract(opentracing.Format.HTTP_HEADERS, properties.headers,
                                         disable_w3c_trace_context=True)

            with tracer.start_active_span("rabbitmq", child_of=parent_span) as scope:
                try:
                    _extract_consumer_tags(scope.span,
                                           conn=instance.connection,
                                           queue=queue)
                except:
                    logger.debug("basic_get_with_instana: ", exc_info=True)

                try:
                    callback(channel, method, properties, body)
                except Exception as e:
                    scope.span.log_exception(e)
                    raise

        args = (queue, _cb_wrapper) + args
        return wrapped(*args, **kwargs)

    @wrapt.patch_function_wrapper('pika.adapters.blocking_connection', 'BlockingChannel.basic_consume')
    def basic_consume_with_instana(wrapped, instance, args, kwargs):
        def _bind_args(queue, on_message_callback, *args, **kwargs):
            return (queue, on_message_callback, args, kwargs)

        queue, on_message_callback, args, kwargs = _bind_args(*args, **kwargs)

        def _cb_wrapper(channel, method, properties, body):
            parent_span = tracer.extract(opentracing.Format.HTTP_HEADERS, properties.headers,
                                         disable_w3c_trace_context=True)

            with tracer.start_active_span("rabbitmq", child_of=parent_span) as scope:
                try:
                    _extract_consumer_tags(scope.span,
                                           conn=instance.connection._impl,
                                           queue=queue)
                except:
                    logger.debug("basic_consume_with_instana: ", exc_info=True)

                try:
                    on_message_callback(channel, method, properties, body)
                except Exception as e:
                    scope.span.log_exception(e)
                    raise

        args = (queue, _cb_wrapper) + args
        return wrapped(*args, **kwargs)


    @wrapt.patch_function_wrapper('pika.adapters.blocking_connection', 'BlockingChannel.consume')
    def consume_with_instana(wrapped, instance, args, kwargs):
        def _bind_args(queue, *args, **kwargs):
            return (queue, args, kwargs)

        (queue, args, kwargs) = (_bind_args(*args, **kwargs))

        def _consume(gen):
            for yilded in gen:
                # Bypass the delivery created due to inactivity timeout
                if yilded is None or not any(yilded):
                    yield yilded
                    continue

                (method_frame, properties, body) = yilded

                parent_span = tracer.extract(opentracing.Format.HTTP_HEADERS, properties.headers,
                                             disable_w3c_trace_context=True)
                with tracer.start_active_span("rabbitmq", child_of=parent_span) as scope:
                    try:
                        _extract_consumer_tags(scope.span,
                                               conn=instance.connection._impl,
                                               queue=queue)
                    except:
                        logger.debug("consume_with_instana: ", exc_info=True)

                    try:
                        yield yilded
                    except Exception as e:
                        scope.span.log_exception(e)
                        raise

        args = (queue,) + args
        res = wrapped(*args, **kwargs)

        if isinstance(res, types.GeneratorType):
            return _consume(res)
        else:
            return res


    @wrapt.patch_function_wrapper('pika.adapters.blocking_connection', 'BlockingChannel.__init__')
    def _BlockingChannel___init__(wrapped, instance, args, kwargs):
        ret = wrapped(*args, **kwargs)
        impl = getattr(instance, '_impl', None)

        if impl and hasattr(impl.basic_consume, '__wrapped__'):
            impl.basic_consume = impl.basic_consume.__wrapped__

        return ret


    wrapt.wrap_function_wrapper('pika.channel', 'Channel.basic_get', basic_get_with_instana)
    wrapt.wrap_function_wrapper('pika.channel', 'Channel.basic_consume', basic_get_with_instana)

    logger.debug("Instrumenting pika")
except ImportError:
    pass
