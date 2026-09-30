# H013 integrated fan result

PASS. Exact approved packet staged and invoked once. All five integrated fans accepted100%, policy1; firmware default policy0 restored after the continuous <=65C/30s interval. Durable ownership cleared. Production service enabled/active/running, exact reviewed source/config/unit hashes in FAN-RESULT.json. Server excluded, no BMC action. Mechanical airflow and sustained thermal performance remain unqualified.

|GPU/fan|Before policy/target/RPM|100% policy/target/RPM|Restored policy/target/RPM|
|---|---|---|---|
|GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237/0|0/30/1201|1/100/2880|0/30/2877|
|GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237/1|0/30/1200|1/100/2873|0/30/2875|
|GPU-69acfa26-8b60-61b5-702d-aee252c163cc/0|0/30/1200|1/100/2874|0/30/2872|
|GPU-69acfa26-8b60-61b5-702d-aee252c163cc/1|0/30/1200|1/100/2876|0/30/2876|
|GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23/0|0/30/999|1/100/3467|0/30/3465|

RPM after restoration can remain high while fans decelerate; policy/target and measured RPM are distinct. Rollback: `sudo systemctl disable --now local-ai-fan-boost.service`; this invokes boost-only StopPost. Preserve /var/lib/local-ai-fan-boost/ownership.json and controller.lock. Never manually clear intent or force firmware defaults. All three installed paths were absent before installation; retained source/config/unit may be removed only after reviewed recovery and hash checks, with Store retained.
