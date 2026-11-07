# Why Argon2id or bcrypt Outperform a Single SHA‑256 Round for Password Storage

## Summary
Passwords should be hashed with Argon2id or bcrypt because these functions are deliberately slow and memory‑hard, making offline brute‑force attacks computationally expensive [1, 2, 3]. A single round of SHA‑256 is too fast; attackers can compute billions of hashes per second, rendering it ineffective as a password‑hashing primitive [2]. Argon2id’s configurable memory requirement and bcrypt’s adjustable work factor allow systems to tune security to current hardware capabilities. Both algorithms are widely supported, have proven implementations, and mitigate side‑channel and time‑memory trade‑off attacks. Choosing between them depends on performance constraints, compatibility, and the desired balance of memory versus CPU cost.  

## Key Features of Argon2id and bcrypt  
Argon2id is a memory‑hard function that forces attackers to supply a configurable amount of RAM for each guess, increasing the cost of parallel attacks [1, 2]. It also balances resistance to side‑channel attacks with time‑memory trade‑offs, providing robustness against both hardware and software optimizations [1]. Bcrypt, introduced in 1999, incorporates a cost factor that directly controls the number of iterations, thereby tuning the hashing speed to desired security levels [3]. Both algorithms include salting by design, preventing pre‑computed rainbow tables and ensuring unique hash outputs per password.  

## Shortcomings of a Single SHA‑256 Round  
SHA‑256 was designed for speed; modern GPUs can compute over 20 billion hashes per second, making it trivial for attackers to test vast password spaces [2]. Even with salting, the raw speed of SHA‑256 remains a vulnerability because salting only thwarts pre‑computed attacks, not real‑time brute‑force attempts [4]. The lack of configurable work factors means that SHA‑256 cannot be tuned to increase computational cost as hardware improves, leaving systems perpetually exposed [4].  

## Computational Cost and Memory Hardness  
Argon2id’s memory hardness forces attackers to allocate significant RAM for each hash calculation, effectively paralyzing GPU and ASIC clusters that rely on massive parallelism [2]. This memory requirement raises the attack cost linearly with the number of guesses, unlike SHA‑256 where cost scales only with CPU cycles. Bcrypt’s cost factor increases the number of expensive Blowfish rounds, raising CPU time per guess. While bcrypt is CPU‑bound, Argon2id’s memory bound makes it more resistant to specialized hardware that can accelerate CPU operations.  

## Practical Considerations for Choosing Argon2id vs. bcrypt  
- **Performance**: Bcrypt typically requires less memory, making it suitable for environments with limited RAM [3].  
- **Compatibility**: Bcrypt has long-standing support across many programming languages and frameworks, whereas Argon2id is newer but increasingly adopted in modern libraries.  
- **Implementation**: Both algorithms have vetted implementations; however, Argon2id’s specification is more recent, and some legacy systems may lack native support.  
- **Security Posture**: Argon2id’s memory hardness offers stronger protection against future GPU/ASIC advances, while bcrypt remains robust against current hardware but may become less effective as processing power grows.  

## Limitations  
- The evidence does not quantify exact performance metrics (hash time per round) for Argon2id or bcrypt relative to SHA‑256.  
- Memory usage per hash for Argon2id is not specified in the provided sources.  
- The sources do not discuss whether multiple rounds of SHA‑256 would mitigate the speed issue.  
- No direct comparison of side‑channel resistance between the two algorithms is provided.

## References

1. Argon2id Password Hashing Guide for Developers — https://md5-encryption.com/blogs/argon2id-password-hashing-guide.html
2. Cryptographic Hashing vs Password Hashing: SHA-256 vs bcrypt & Argon2 | DevUtils — https://www.devutils.run/guides/cryptographic-hashing-sha256-vs-bcrypt
3. SHA-256 vs bcrypt vs Argon2: Password Hashing Compared — https://freeutil.app/blog/sha256-vs-bcrypt-vs-argon2/
4. Password Hashing — why SHA-256 fails, and what to use instead — https://devholster.com/blog/password-hashing-guide/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | Argon2id balances resistance to side‑channel attacks with resistance to time‑memory trade‑offs. | "Argon2id is a password-hashing and key-derivation function designed to make offline guessing expensive. It combines features of Argon2i and Argon2d to" | 351-587 |
| [1] | Argon2 consumes a configurable amount of memory for each operation, requiring attackers to supply that memory  | "Argon2 consumes a configurable amount of memory for each operation. Large-scale attackers must provide that memory and its bandwidth for every paralle" | 1786-1961 |
| [2] | SHA‑256 is extremely fast, with modern GPUs able to compute over 20 billion hashes per second. | "Modern consumer GPUs (like an NVIDIA RTX 4090) can calculate over 20 billion SHA-256 hashes per second." | 904-1007 |
| [2] | Argon2id is memory‑hard, requiring dedicated RAM bandwidth per hash calculation, which effectively paralyzes G | "Argon2id is the gold standard for modern applications. It is memory-hard, requiring dedicated RAM bandwidth per hash calculation, which effectively pa" | 418-619 |
| [3] | bcrypt uses a configurable work factor that controls how slow the hashing is. | "bcrypt was designed in 1999 specifically for password hashing. Its key feature is a configurable work factor (cost factor) — a parameter that controls" | 351-526 |
| [4] | SHA‑256 is fast, making it unsuitable for password hashing because attackers can compute billions of hashes pe | "It’s wrong for passwords for a different reason entirely: it was designed to be fast, and password hashing is the one job where speed works for the at" | 143-300 |
| [4] | Salting does not mitigate the speed issue of SHA‑256. | "Salting stops precomputed rainbow tables but does nothing about that raw speed." | 1757-1836 |

---
*7 passages from 4 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*